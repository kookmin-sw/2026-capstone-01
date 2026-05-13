"""RDB instrumentation — route 매핑 / 트랜잭션 카운트 / SQLAlchemy 이벤트 부착.

contextvar 기반 task-local route 라벨로 query duration 을 도메인 단위 카디널리티로 통제.
pool gauge 는 query 직후 + event_loop 의 1초 폴링 양쪽에서 fresh 유지.
"""
import time
from sqlalchemy import event

from app.core.context import db_route_var
from app.core.metric import (
    DB_POOL_CHECKED_OUT,
    DB_POOL_SIZE,
    DB_QUERY_DURATION,
    DB_TRANSACTION_TOTAL,
)


# route 라벨 enum (도메인 단위, /api/{domain}/... 매핑).
# 카디널리티 폭증 방지: endpoint 별 X, 도메인 단위 ~10 enum.
_DB_ROUTE_DOMAINS = frozenset({
    "auth", "chat", "tour", "friend", "feed",
    "notification", "tripmate", "menu_ai", "translation", "public",
})

# DB transaction result enum.
DB_TRANSACTION_RESULTS = ("commit", "rollback", "other")


# attach_db_instrumentation 에서 저장. event_loop 의 lag loop 가 풀 gauge 를 1 초마다 갱신
# 할 때 참조한다. event_loop 모듈이 _get_pool_engine / _reset_pool_engine 으로만 접근하므로
# 모듈 분리 후에도 단일 source of truth 유지.
_db_engine_for_pool_gauge = None


def _get_pool_engine():
    """event_loop._event_loop_lag_loop 가 매 tick 호출. 미부착 상태면 None."""
    return _db_engine_for_pool_gauge


def _reset_pool_engine() -> None:
    """event_loop.stop_event_loop_monitor 가 shutdown 에서 호출.

    pytest 등에서 lifespan 을 여러 번 진입할 때 stale engine 참조가 module level 에 남아
    GC 를 막거나 다음 사이클로 leak 되는 것을 차단. attach_db_instrumentation 가 다음
    호출에서 새 engine 으로 다시 셋팅하므로 정상 동작.
    """
    global _db_engine_for_pool_gauge
    _db_engine_for_pool_gauge = None


def db_route_for_path(path: str) -> str:
    """HTTP path 를 도메인 단위 route 라벨로 매핑.

    /health 류는 'health', /api/{domain}/... 는 domain (화이트리스트만).
    그 외는 'other' 로 통합 — 카디널리티 폭증 차단.
    """
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
    """UoW __aexit__ 에서 commit / rollback / other 분기 카운트."""
    DB_TRANSACTION_TOTAL.labels(route=route, result=result).inc()


def attach_db_instrumentation(async_engine) -> None:
    """SQLAlchemy AsyncEngine 에 query duration / pool gauge 이벤트 리스너 부착.

    main.py lifespan startup 에서 engine 인스턴스 1 회 받아 호출.
    이벤트는 async engine 의 sync_engine 에 등록 — asyncpg 드라이버에서도 정상 작동.

    멱등 보장 (`_krip_instrumented` flag): 같은 engine 인스턴스에 두 번 호출되면 listener
    재등록을 skip. listener 중복 시 매 query 가 2회 observe 되어 p99 분포가 어긋나는
    사고 차단. pytest 등에서 lifespan 을 여러 번 진입하는 시나리오 핵심.

    flag 부착 대상은 `sync_engine` 이다 — AsyncEngine 은 __slots__ 가 정의된 클래스라
    동적 attribute 할당이 AttributeError 로 실패한다 (`obj._krip_... = True` 가 raise).
    sync_engine (sqlalchemy.engine.Engine) 은 일반 클래스라 안전. 같은 AsyncEngine 은
    같은 sync_engine 인스턴스를 보장하므로 멱등성 의미 그대로 보존된다.
    SQLAlchemy 가 향후 sync_engine 도 __slots__ 로 바꾸면 WeakSet 같은 모듈 set 으로
    fallback 필요. **다시 async_engine 에 박지 말 것** — 이 사고의 출발점.

    `_db_engine_for_pool_gauge` global 은 flag 체크보다 먼저 셋팅 — stop_event_loop_monitor
    가 None 으로 리셋한 뒤 같은 engine 재attach 시에도 lag loop 가 pool gauge 정상 갱신.
    flag 가 막는 것은 listener 등록뿐, engine reference 는 항상 최신.

    contextvar 는 task-local 이라 sync 콜백이 async task 에서 호출되어도 같은 task 의
    db_route_var 에 정상 접근.

    pool gauge 는 here 와 _event_loop_lag_loop 양쪽에서 갱신:
      - here: query 직후 fresh
      - loop: 트래픽 0 일 때도 1 초 주기로 fresh
    두 경로 모두 같은 prometheus_client Gauge 라 race-safe.
    """
    global _db_engine_for_pool_gauge
    _db_engine_for_pool_gauge = async_engine

    sync_engine = async_engine.sync_engine

    if getattr(sync_engine, "_krip_instrumented", False):
        return

    # 첫 priming — _event_loop_lag_loop 첫 tick 전에 한 번 set.
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

        # 풀 gauge 매 query 시점 갱신 — 별도 background task 없이 항상 fresh.
        try:
            pool = sync_engine.pool
            DB_POOL_CHECKED_OUT.set(pool.checkedout())
            DB_POOL_SIZE.set(pool.size())
        except Exception:
            pass

    sync_engine._krip_instrumented = True
