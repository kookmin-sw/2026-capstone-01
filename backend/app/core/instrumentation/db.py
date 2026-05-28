"""RDB instrumentation — route 매핑 / 트랜잭션 카운트 / SQLAlchemy 이벤트 부착.

contextvar 기반 task-local route 라벨로 query duration 을 도메인 단위 카디널리티로 통제.
pool gauge 는 query 직후 + event_loop 의 1초 폴링 양쪽에서 fresh 유지.
"""
import time
from sqlalchemy import event

from app.core.metric import (
    DB_POOL_CHECKED_OUT,
    DB_POOL_SIZE,
    DB_QUERY_DURATION,
    DB_TRANSACTION_TOTAL,
)
from app.core.context import db_route_var


# route 라벨 enum — endpoint 단위 X, 도메인 단위 ~10개로 카디널리티 통제.
_DB_ROUTE_DOMAINS = frozenset({
    "auth", "chat", "tour", "friend", "feed",
    "notification", "tripmate", "menu_ai", "translation", "public",
})

DB_TRANSACTION_RESULTS = ("commit", "rollback", "other")


# attach_db_instrumentation 가 저장 → event_loop 의 lag loop 가 pool gauge 갱신 시 참조.
_db_engine_for_pool_gauge = None


def _get_pool_engine():
    """event_loop._event_loop_lag_loop 가 매 tick 호출. 미부착 상태면 None."""
    return _db_engine_for_pool_gauge


def _reset_pool_engine() -> None:
    """shutdown 에서 호출 — pytest 등 lifespan 재진입 시 stale engine 누수 차단."""
    global _db_engine_for_pool_gauge
    _db_engine_for_pool_gauge = None


def db_route_for_path(path: str) -> str:
    """HTTP path → 도메인 라벨. /health 류는 'health', 화이트리스트 외는 'other'."""
    if path == "/health" or path == "/health/deep" or path == "/ready":
        return "health"
    if path.startswith("/api/"):
        # /api/{domain}/... → 세 번째 segment 가 domain.
        parts = path.split("/", 3)
        if len(parts) >= 3:
            domain = parts[2]
            if domain in _DB_ROUTE_DOMAINS:
                return domain
    return "other"


def db_transaction_inc(route: str, result: str) -> None:
    """UoW __aexit__ 의 commit / rollback / other 분기 카운트."""
    DB_TRANSACTION_TOTAL.labels(route=route, result=result).inc()


def attach_db_instrumentation(async_engine) -> None:
    """SQLAlchemy AsyncEngine 에 query duration / pool gauge 이벤트 부착. main.py lifespan 에서 1회.

    멱등 (`_krip_instrumented` flag) — 중복 listener 등록 시 매 query 가 2회 observe 되어
    p99 분포가 어긋나는 사고 차단. pytest 의 lifespan 재진입 핵심.

    flag 는 `sync_engine` 에 부착 — AsyncEngine 은 `__slots__` 라 동적 attr 가 AttributeError.
    sync_engine 은 일반 클래스라 안전, 같은 AsyncEngine 은 같은 sync_engine 인스턴스를 보장.
    SQLAlchemy 가 향후 sync_engine 도 __slots__ 로 바꾸면 WeakSet 같은 모듈 set 으로 fallback 필요.
    **다시 async_engine 에 박지 말 것** — 이 사고의 출발점.

    `_db_engine_for_pool_gauge` 는 flag 체크보다 먼저 셋팅 — reset 후 같은 engine 재attach 시에도
    lag loop 가 pool gauge 정상 갱신 (flag 가 막는 건 listener 등록뿐).
    """
    global _db_engine_for_pool_gauge
    _db_engine_for_pool_gauge = async_engine

    sync_engine = async_engine.sync_engine

    if getattr(sync_engine, "_krip_instrumented", False):
        return

    # 첫 priming — lag loop 의 첫 tick 전에 한 번.
    try:
        DB_POOL_CHECKED_OUT.set(sync_engine.pool.checkedout())
        DB_POOL_SIZE.set(sync_engine.pool.size())
    except Exception:
        pass

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _on_before(conn, cursor, statement, parameters, context, executemany):
        context._krip_query_start = time.perf_counter()

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _on_after(conn, cursor, statement, parameters, context, executemany):
        started = getattr(context, "_krip_query_start", None)
        if started is None:
            return
        elapsed = time.perf_counter() - started
        route = db_route_var.get()
        DB_QUERY_DURATION.labels(route=route).observe(elapsed)

        # 매 query 시점에 pool gauge 도 갱신 — 별도 background task 없이 항상 fresh.
        try:
            pool = sync_engine.pool
            DB_POOL_CHECKED_OUT.set(pool.checkedout())
            DB_POOL_SIZE.set(pool.size())
        except Exception:
            pass

    sync_engine._krip_instrumented = True
