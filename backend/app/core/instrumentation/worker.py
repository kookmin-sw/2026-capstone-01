"""워커 tick liveness 관측 — reconcile / node_heartbeat / fanout_dispatch / withdraw_purge."""
import time
from contextlib import asynccontextmanager
import asyncio

from app.core.metric import (
    WITHDRAW_PURGE_LAST_RUN_DURATION,
    WORKER_LAST_TICK_TIMESTAMP,
    WORKER_TICK_DURATION,
    WORKER_TICK_TOTAL,
)
from app.core.context import db_route_var
from app.config.setting import settings


WORKER_NAMES = ("reconcile", "node_heartbeat", "fanout_dispatch", "withdraw_purge")

# FANOUT_MODE=node_channel 일 때만 실제로 도는 워커.
# in_process 모드에서 prime 만 해두면 startup 시각이 박힌 채 갱신되지 않아 NODE_TTL 후
# WorkerStale 이 만성 false-positive 로 발화한다 — prime 도 skip 해야 함.
_NODE_CHANNEL_ONLY_WORKERS = frozenset({"node_heartbeat", "fanout_dispatch"})


# 워커 → DB route 매핑. 워커 task 의 task-local route 를 자동 셋팅해 워커 query 가
# 도메인 라벨로 db_query_duration_seconds 에 합쳐진다 (워커 enum 추가 없이 카디널리티 통제).
_WORKER_TO_ROUTE = {
    "reconcile": "chat",
    "node_heartbeat": "chat",
    "fanout_dispatch": "chat",
    "withdraw_purge": "auth",
}


@asynccontextmanager
async def worker_tick(worker: str):
    """워커 1 tick 의 결과 / 시간 / 마지막 발화 시각 관측.

    result 라벨:
    - `cancelled` : asyncio.CancelledError (shutdown 신호 — 알람이 자연 제외)
    - `error`     : Exception
    - `ok`        : 정상

    last_tick_timestamp 는 성공/실패/취소 무관하게 매 tick 끝에 갱신 — WorkerStale 알람의
    "최근에 깨어났는가" 의도에 맞춤. DB route 도 자동 셋팅돼 워커 내부 쿼리가 올바른 라벨링.
    """
    nid = settings.NODE_ID
    route = _WORKER_TO_ROUTE.get(worker, "other")
    route_token = db_route_var.set(route)
    started = time.perf_counter()
    result = "ok"
    try:
        yield
    except asyncio.CancelledError:
        result = "cancelled"
        raise
    except Exception:
        result = "error"
        raise
    finally:
        db_route_var.reset(route_token)
        elapsed = time.perf_counter() - started
        WORKER_TICK_TOTAL.labels(worker=worker, node_id=nid, result=result).inc()
        WORKER_TICK_DURATION.labels(worker=worker, node_id=nid).observe(elapsed)
        WORKER_LAST_TICK_TIMESTAMP.labels(worker=worker, node_id=nid).set(time.time())


@asynccontextmanager
async def withdraw_purge_run():
    """일일 1회 발화하는 withdraw_purge 사이클 측정.

    1건/일 이라 분포가 의미 없어 Gauge 사용. last_tick_timestamp 는 다른 워커와 동일 라벨로
    갱신해 WorkerStale 알람 통일.
    """
    nid = settings.NODE_ID
    route_token = db_route_var.set("auth")
    started = time.perf_counter()
    try:
        yield
    finally:
        db_route_var.reset(route_token)
        elapsed = time.perf_counter() - started
        WITHDRAW_PURGE_LAST_RUN_DURATION.labels(node_id=nid).set(elapsed)
        WORKER_LAST_TICK_TIMESTAMP.labels(worker="withdraw_purge", node_id=nid).set(time.time())


def prime_worker_gauges() -> None:
    """lifespan startup 직후 활성 워커 last_tick_timestamp 를 startup 시각으로 priming.

    첫 tick 전까지 false-negative WorkerStale 차단.
    `FANOUT_MODE=in_process` 에선 node_channel 전용 워커가 안 돌므로 priming 도 skip
    (series 부재 → 알람 규칙이 자연 미발화).
    """
    nid = settings.NODE_ID
    now = time.time()
    skip_workers = (
        _NODE_CHANNEL_ONLY_WORKERS
        if settings.FANOUT_MODE != "node_channel"
        else frozenset()
    )
    for w in WORKER_NAMES:
        if w in skip_workers:
            continue
        WORKER_LAST_TICK_TIMESTAMP.labels(worker=w, node_id=nid).set(now)
