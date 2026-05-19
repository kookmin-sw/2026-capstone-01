"""워커 tick liveness 관측.

reconcile / node_heartbeat / fanout_dispatch / withdraw_purge 의 tick 단위 결과 /
시간 / 마지막 발화 시각을 단일 컨텍스트 매니저로 통일한다.
"""
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
# in_process 모드에선 start_node_registry / start_fanout_dispatcher 가 즉시 return 하므로
# prime 만 해두면 startup 시각이 박힌 채 갱신되지 않아 NODE_TTL 후 WorkerStale 이
# 만성 false-positive 로 발화한다 (prime_worker_gauges 의 mode 분기 근거).
_NODE_CHANNEL_ONLY_WORKERS = frozenset({"node_heartbeat", "fanout_dispatch"})


# 워커 → DB route 매핑. 워커 task 의 task-local route 를 자동 셋팅해 워커 query 가
# 도메인 단위 라벨로 db_query_duration_seconds 에 합쳐진다 (워커 enum 추가 없음, 카디널리티 통제).
_WORKER_TO_ROUTE = {
    "reconcile": "chat",
    "node_heartbeat": "chat",
    "fanout_dispatch": "chat",
    "withdraw_purge": "auth",
}


@asynccontextmanager
async def worker_tick(worker: str):
    """워커 1 tick 의 결과 / 시간 / 마지막 발화 시각을 동시에 관측한다.

    예외 분류 (result 라벨):
      - asyncio.CancelledError → "cancelled". shutdown 신호이므로 "ok" / "error" 와 다른
        의미. 알람 룰이 `result="error"` 만 보면 cancel 을 자연 제외 — false-positive 차단.
      - Exception → "error".
    raise 는 그대로 전파. 호출 측이 swallow 할지 propagate 할지 결정.

    last_tick_timestamp 는 성공 / 실패 / 취소 무관하게 매 tick 끝에 갱신된다.
    WorkerStale 알람의 의도가 "최근에 깨어났는가" 라 cancel 도 liveness 신호로 보며,
    shutdown cancel 직후엔 어차피 컨테이너 종료라 scrape 미도달 — 갱신 여부 무관.

    DB route 도 함께 자동 셋팅 — 워커 안에서 실행되는 RDB 쿼리가 올바른 도메인 라벨로 잡힌다.
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
    """일일 1 회 발화하는 withdraw_purge 사이클 측정.

    매일 1 건이라 Histogram 의 분포가 의미 없어 Gauge 로 둔다.
    last_tick_timestamp 는 다른 워커와 동일한 라벨 체계로 갱신해 WorkerStale 알람을 통일한다.
    DB route 는 'auth' 로 셋팅 — 사이클 내 RDB / Mongo 쿼리가 auth 도메인으로 라벨된다.
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

    초기 부팅 후 첫 tick 전까지 false-negative WorkerStale 알람을 차단한다.

    FANOUT_MODE=in_process 모드에선 node_heartbeat / fanout_dispatch 워커가 실제로
    돌지 않으므로 prime 도 skip — prime 만 해두면 startup 시각이 박힌 채 갱신되지 않아
    NODE_TTL 후 WorkerStale 이 만성 false-positive 로 발화한다. series 부재면 알람
    룰 (`time() - worker_last_tick_timestamp > THRESHOLD`) 이 자연 미발화하므로 룰 측
    mode 분기 불필요.
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
