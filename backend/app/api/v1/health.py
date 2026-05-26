"""헬스체크 엔드포인트 — /health, /health/deep, /ready.

3종 분리:
  - /health (liveness): 프로세스 기동 여부만 본다. k8s livenessProbe 와 Watchdog 이 호출한다.
                        모델 reload 나 트래픽 급증 중에도 프로세스가 살아 있으면 200 을 반환한다.
  - /health/deep      : Postgres SELECT 1, Mongo ping, Redis hot, Redis dedupe 4종 ping 을
                        asyncio.gather 로 동시에 실행해 max(store_latency) 가 응답 시간이 되도록 한다.
                        blackbox 와 운영자 진단용이며 scrape_timeout 안에 안전하게 수렴한다.
  - /ready (readiness): /health/deep 4-ping 통과에 더해 AI 모델 3종(Tour Planner, Menu OCR,
                        Papago Translator) 의 _initialized=True 가 모두 만족돼야 200 을 반환한다.

라우팅: app/main.py 가 app.include_router(health_router) 로 등록한다.
api_router 의 /api prefix 를 우회해 k8s probe 와 blackbox 가 직접 도달할 수 있게 한다.
"""
import time
from sqlalchemy import text
from fastapi.responses import JSONResponse
from fastapi import APIRouter, Request
import asyncio

from app.database.session import mongodb
from app.core.redis import get_redis_client, get_redis_dedupe_client
from app.core.metric import DEEP_CANARY_DURATION
from app.core.logger import get_logger
from app.core.ai.tour_planner.load import TourPlanner
from app.core.ai.papago_translator.load import PapagoTranslator
from app.core.ai.menu_ocr.load import MenuOcr


logger = get_logger("health")
router = APIRouter(tags=["health"])


# 개별 store ping 의 상한 — 한 곳이 hang 해도 gather 가 budget 안에 수렴해야
# scrape_timeout 후 서버 측 coroutine 이 pile-up 되는 것을 막는다.
# 정상 ping 은 수 ms 수준이라 2 초면 여유롭게 끝나고, 그보다 오래 걸리면 사실상 장애.
_PING_TIMEOUT_SECONDS = 2.0


# ──────────────────── liveness ────────────────────


@router.get("/health")
async def liveness() -> JSONResponse:
    """프로세스 기동 여부만 확인한다. 모델 로드가 끝나지 않아도 200 을 반환한다."""
    return JSONResponse(status_code=200, content={"status": "ok"})


# ──────────────────── deep canary (4-ping 병렬) ────────────────────


async def _pg_ping(request: Request) -> bool:
    """Postgres 에 SELECT 1 한 번. UoW 를 거치지 않고 session_factory 를 직접 쓴다.

    UoW.__aexit__ 가 DB_TRANSACTION_TOTAL{route, result=commit|rollback|other} 을
    카운트하므로, health-check SELECT 1 까지 UoW 로 감싸면 트랜잭션 카운터가 health
    트래픽으로 도배된다 — 사용자 commit/rollback 비율 분석이 흐려진다. UoW 우회로
    카운터는 사용자 트래픽만 보존한다.

    DB_QUERY_DURATION{route="health"} 은 정상적으로 발화한다. attach_db_instrumentation
    이 sync_engine 의 before/after_cursor_execute 이벤트에 listen 하므로 UoW 와 무관하게
    cursor 단계에서 관측되고, db_route_var 는 RequestIDMiddleware 가 /health* 경로에서
    "health" 로 set 한 상태라 라벨도 정확하다.
    """
    session_factory = request.app.container.session_factory()
    async with session_factory() as session:
        await session.execute(text("SELECT 1"))
    return True


async def _mongo_ping() -> bool:
    """Mongo admin 에 ping 명령을 보낸다. database/session.py 의 mongodb 모듈을 사용한다."""
    if mongodb.client is None:
        raise RuntimeError("mongodb client not initialized")
    await mongodb.client.admin.command("ping")
    return True


async def _redis_hot_ping() -> bool:
    client = await get_redis_client()
    await client.ping()
    return True


async def _redis_dedupe_ping() -> bool:
    client = await get_redis_dedupe_client()
    await client.ping()
    return True


async def _run_deep_pings(request: Request) -> dict[str, object]:
    """4종 store 의 ping 을 동시에 실행한다.

    name → coroutine 페어를 dict 하나에 모아 라벨/실행 순서를 단일 source-of-truth 로 묶는다.
    이전 구조는 _summarize 의 names 리스트와 gather 인자 순서가 암묵 결합돼 있어
    gather 순서를 누군가 바꾸면 라벨이 silent 하게 mis-map 됐다 (예: postgres 실패가
    mongodb 로 보고). dict 는 Python 3.7+ 에서 삽입 순서가 보존되므로 keys/values 가
    같은 순서로 iterate 된다.

    각 ping 은 asyncio.wait_for 로 per-ping budget 을 강제한다.
    드라이버 기본 timeout (예: motor serverSelectionTimeoutMS=30s, redis-py socket_timeout=None)
    은 너무 길거나 무한 대기라 health 핸들러를 잡아두면 Prometheus scrape_timeout 후에도
    coroutine 이 살아남아 pile-up 된다. TimeoutError 는 _summarize 가 fail 로 흡수한다.
    """
    pings = {
        "postgres": _pg_ping(request),
        "mongodb": _mongo_ping(),
        "redis_hot": _redis_hot_ping(),
        "redis_dedupe": _redis_dedupe_ping(),
    }
    results = await asyncio.gather(
        *(asyncio.wait_for(coro, timeout=_PING_TIMEOUT_SECONDS) for coro in pings.values()),
        return_exceptions=True,
    )
    return dict(zip(pings.keys(), results))


def _summarize(results: dict[str, object]) -> dict:
    """_run_deep_pings 결과 dict 를 store 별 ok 또는 예외 타입명으로 정리한다."""
    summary: dict[str, str] = {}
    failed: list[str] = []
    for name, r in results.items():
        if isinstance(r, BaseException):
            summary[name] = type(r).__name__
            failed.append(name)
        else:
            summary[name] = "ok"
    return {"summary": summary, "failed": failed}


@router.get("/health/deep")
async def deep_health(request: Request) -> JSONResponse:
    """Postgres, Mongo, Redis hot, Redis dedupe 4-ping 을 병렬로 수행한다.

    한 곳이라도 실패하면 503 을 반환한다.
    응답 시간은 deep_canary_duration_seconds 히스토그램에 result 라벨로 관측한다.
    이 핸들러는 사용자 트래픽 RED 메트릭에서는 제외해 외부 의존성 ping 으로 분포가 왜곡되지 않게 한다.

    canary 메트릭은 이 핸들러에서만 observe 한다 — /ready 도 같은 4-ping 을 호출하지만
    히스토그램에 기록하지 않는다. /ready 는 k8s readinessProbe 가 ~10s 주기로 fire 하는
    반면 /health/deep 은 blackbox / 운영자가 ~1m 주기로 호출하므로, 양쪽을 같은 히스토그램에
    섞으면 readiness 트래픽이 deep canary 분포를 흡수해 SLI 의 의미가 사라진다.
    """
    started = time.perf_counter()
    results = await _run_deep_pings(request)
    elapsed = time.perf_counter() - started

    body = _summarize(results)
    if body["failed"]:
        DEEP_CANARY_DURATION.labels(result="fail").observe(elapsed)
        logger.warning("health/deep 실패: {}", body)
        return JSONResponse(status_code=503, content={"status": "fail", **body})

    DEEP_CANARY_DURATION.labels(result="ok").observe(elapsed)
    return JSONResponse(status_code=200, content={"status": "ok", **body})


# ──────────────────── readiness ────────────────────


def _ai_models_ready() -> tuple[bool, dict[str, bool]]:
    """AI 모델 3종 싱글톤의 _initialized 플래그를 모은다.

    각 모델은 __new__ 패턴으로 _initialized=False 로 셋업되고 load() 가 끝나면 True 가 된다.
    getattr fallback 으로 인터페이스가 바뀌어도 KeyError 가 나지 않게 한다.
    """
    flags = {
        "tour_planner": getattr(TourPlanner(), "_initialized", False),
        "menu_ocr": getattr(MenuOcr(), "_initialized", False),
        "papago_translator": getattr(PapagoTranslator(), "_initialized", False),
    }
    return all(flags.values()), flags


@router.get("/ready")
async def readiness(request: Request) -> JSONResponse:
    """/health/deep 4-ping 통과와 AI 모델 로드 완료를 모두 만족할 때만 200 을 반환한다.

    deep_canary_duration_seconds 는 일부러 observe 하지 않는다. readinessProbe 는
    ~10s 주기로 fire 되므로 같은 히스토그램에 섞이면 분당 1회 수준인 /health/deep canary
    분포가 readiness 샘플에 흡수되어 SLI 신호가 사라진다. /ready 의 latency 자체가
    필요해질 때는 별도 메트릭(예: readiness_probe_duration_seconds) 으로 분리한다.

    AI 모델 미로딩 시점에는 store ping 을 아예 실행하지 않는다 — 어차피 503 이 확정이라
    startup 중 불필요한 4-ping I/O 를 줄인다. 이때 summary/failed 는 빈 값으로 채워
    어느 분기에서도 응답 스키마가 동일하게 유지된다 (alert/dashboard parser 의 분기 제거).

    응답 키 (모든 분기 공통):
      - status               : "ok" | "fail"
      - summary              : {store_name: "ok" | <ExceptionTypeName>} — AI block 단계면 {}
      - failed               : [store_name, ...] — store ping 실패 목록
      - ai_models            : {model_name: bool} — 3 종 _initialized 플래그
      - ai_models_not_loaded : [model_name, ...] — 미로딩 모델 목록
    """
    ai_ok, flags = _ai_models_ready()
    not_loaded = [name for name, loaded in flags.items() if not loaded]

    if not ai_ok:
        return JSONResponse(
            status_code=503,
            content={
                "status": "fail",
                "summary": {},
                "failed": [],
                "ai_models": flags,
                "ai_models_not_loaded": not_loaded,
            },
        )

    results = await _run_deep_pings(request)
    body = _summarize(results)
    payload = {**body, "ai_models": flags, "ai_models_not_loaded": not_loaded}
    status_code = 503 if body["failed"] else 200
    status = "fail" if body["failed"] else "ok"
    return JSONResponse(status_code=status_code, content={"status": status, **payload})
