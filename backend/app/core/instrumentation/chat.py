"""Chat 도메인 instrumentation — WS / fan-out / reconcile / unread.

모든 라벨은 화이트리스트 정규화로 카디널리티 누수 차단.
"""
import time
from contextlib import asynccontextmanager

from app.core.metric import (
    CHAT_ACTIVE_NODES,
    CHAT_FANOUT_DISPATCH_DURATION,
    CHAT_FANOUT_DISPATCH_TOTAL,
    CHAT_FANOUT_PUBLISH_TOTAL,
    CHAT_MESSAGE_SEND_DURATION,
    CHAT_NODE_HEARTBEAT_FAILURES,
    CHAT_RECONCILE_BATCH_POP_TOTAL,
    CHAT_RECONCILE_DIRTY_SET_SIZE,
    CHAT_RECONCILE_ROOMS_PROCESSED_TOTAL,
    CHAT_RECONCILE_TICK_DURATION,
    CHAT_UNREAD_RECOVER_TOTAL,
    CHAT_WS_ACTIVE_CONNECTIONS,
    CHAT_WS_CONNECT_TOTAL,
    CHAT_WS_OP_TOTAL,
    WORKER_LAST_TICK_TIMESTAMP,
)
from app.config.setting import settings


# ────────────────────────────────────────────────────────────────────
# WS 연결 / op
# ────────────────────────────────────────────────────────────────────

CHAT_WS_CONNECT_RESULTS = ("ok", "origin_denied", "auth_expired", "auth_inactive", "session_failed", "other")

CHAT_WS_OP_RESULTS = ("ok", "permission_denied", "validation", "not_found", "upstream", "other")
_KNOWN_WS_OP_RESULTS = frozenset(CHAT_WS_OP_RESULTS)

# ClientRequest discriminated union 의 3 종. 악성 클라의 임의 op 는 'other' 통합.
_KNOWN_WS_OPS = frozenset({"send", "refresh", "read"})


def _normalize_ws_op(op) -> str:
    if isinstance(op, str) and op in _KNOWN_WS_OPS:
        return op
    return "other"


def chat_ws_connect_result(result: str) -> None:
    """WS 연결 시도 결과 카운트."""
    label = result if result in CHAT_WS_CONNECT_RESULTS else "other"
    CHAT_WS_CONNECT_TOTAL.labels(result=label).inc()


def chat_ws_connection_inc() -> None:
    CHAT_WS_ACTIVE_CONNECTIONS.labels(node_id=settings.NODE_ID).inc()


def chat_ws_connection_dec() -> None:
    CHAT_WS_ACTIVE_CONNECTIONS.labels(node_id=settings.NODE_ID).dec()


def _classify_ws_op_error(exc: BaseException) -> str:
    """예외 → result 라벨.

    우선순위 (specific → general):
    1. `exc.error_kind` 자체분류 — 도메인 커스텀 예외가 self-classify. ValueError subclass
       (ChatRoomNotFoundError 등) 가 isinstance 보다 먼저 잡혀야 'validation' 오분류 차단.
    2. `PermissionError` (builtin — 속성 부여 불가).
    3. `ValueError` — pydantic ValidationError 포함.
    4. 'other'.

    화이트리스트 외 error_kind 는 'other' 로 통합.
    """
    kind = getattr(exc, "error_kind", None)
    if isinstance(kind, str) and kind in _KNOWN_WS_OP_RESULTS:
        return kind

    if isinstance(exc, PermissionError):
        return "permission_denied"
    if isinstance(exc, ValueError):
        return "validation"
    return "other"


@asynccontextmanager
async def chat_ws_op(op: str):
    """WS op 1건의 결과 카운트. 예외는 result 라벨 분류 후 그대로 raise."""
    label = _normalize_ws_op(op)
    result = "ok"
    try:
        yield
    except Exception as exc:
        result = _classify_ws_op_error(exc)
        raise
    finally:
        CHAT_WS_OP_TOTAL.labels(op=label, result=result).inc()


def chat_ws_op_validation_failure(op_label: str) -> None:
    """파싱 단계 (Pydantic ValidationError) 카운트."""
    CHAT_WS_OP_TOTAL.labels(op=_normalize_ws_op(op_label), result="validation").inc()


@asynccontextmanager
async def chat_message_send_timer(fanout_path: str):
    """메시지 송신 → fan-out latency. `fanout_path`: local | cross_node."""
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started
        CHAT_MESSAGE_SEND_DURATION.labels(fanout_path=fanout_path).observe(elapsed)


# ────────────────────────────────────────────────────────────────────
# Fan-out publish / dispatch
# ────────────────────────────────────────────────────────────────────

# 다른 노드 envelope 도 받아 unknown op 가능 → 'other' 통합.
_KNOWN_FANOUT_OPS = frozenset({"room", "user", "session", "subscribe", "unsubscribe"})


def _normalize_fanout_op(op) -> str:
    if isinstance(op, str) and op in _KNOWN_FANOUT_OPS:
        return op
    return "other"


def chat_fanout_publish_inc(op: str) -> None:
    """publish 1건 카운트."""
    CHAT_FANOUT_PUBLISH_TOTAL.labels(op=_normalize_fanout_op(op)).inc()


def chat_fanout_dispatch_alive() -> None:
    """polling iteration 마다 last_tick_timestamp 갱신 — envelope 0 건 idle 디스패처의 liveness 유지."""
    WORKER_LAST_TICK_TIMESTAMP.labels(
        worker="fanout_dispatch", node_id=settings.NODE_ID,
    ).set(time.time())


@asynccontextmanager
async def chat_fanout_dispatch(op: str):
    """디스패처가 envelope 1건 처리하는 시간 + 결과. 예외는 result=other 후 그대로 raise."""
    label = _normalize_fanout_op(op)
    started = time.perf_counter()
    result = "ok"
    try:
        yield
    except Exception:
        result = "other"
        raise
    finally:
        elapsed = time.perf_counter() - started
        CHAT_FANOUT_DISPATCH_TOTAL.labels(op=label, result=result).inc()
        CHAT_FANOUT_DISPATCH_DURATION.labels(op=label).observe(elapsed)


def chat_active_nodes_set(value: int) -> None:
    """node_registry heartbeat tick 에서 호출 — ZSET 활성 노드 수 set."""
    CHAT_ACTIVE_NODES.set(value)


def chat_node_heartbeat_failure() -> None:
    CHAT_NODE_HEARTBEAT_FAILURES.labels(node_id=settings.NODE_ID).inc()


# ────────────────────────────────────────────────────────────────────
# Reconcile / Unread recover
# ────────────────────────────────────────────────────────────────────

# batch_pop result:
# - empty        : SET 비어 0건 pop
# - ok           : Mongo aggregate + RDB commit 모두 성공 (partial UPDATE 실패는 outcome=failed)
# - mongo_failed : Mongo 실패 → 배치 통째 재적재
# - rdb_failed   : commit 실패 → 배치 통째 재적재
# - other        : catch-all
CHAT_RECONCILE_BATCH_RESULTS = ("empty", "ok", "mongo_failed", "rdb_failed", "other")

# rooms_processed outcome:
# - updated : UPDATE 성공
# - skipped : Mongo hit 0 (방 생성 직후 삭제 등)
# - failed  : 단일 방 UPDATE 실패 → 그 방만 재적재
CHAT_RECONCILE_OUTCOMES = ("updated", "skipped", "failed")

# unread_recover result:
# - ok             : 정상 종료 (활성 방 없음 또는 counts 반영 완료)
# - redis_failed   : pipeline 실패 후 DEL 정리 성공
# - cleanup_failed : DEL 도 실패 — partial state 잔존 (관측 필요)
# - other          : catch-all
CHAT_UNREAD_RECOVER_RESULTS = ("ok", "redis_failed", "cleanup_failed", "other")


def chat_reconcile_dirty_set_size_set(value: int) -> None:
    """매 tick 시작 시 SCARD 결과 set."""
    CHAT_RECONCILE_DIRTY_SET_SIZE.set(value)


def chat_reconcile_batch_pop_inc(result: str) -> None:
    label = result if result in CHAT_RECONCILE_BATCH_RESULTS else "other"
    CHAT_RECONCILE_BATCH_POP_TOTAL.labels(result=label).inc()


def chat_reconcile_rooms_processed_inc(outcome: str, count: int = 1) -> None:
    """count > 0 일 때만 카운트 — 0 시리즈 등록 방지."""
    if count <= 0:
        return
    label = outcome if outcome in CHAT_RECONCILE_OUTCOMES else "other"
    CHAT_RECONCILE_ROOMS_PROCESSED_TOTAL.labels(outcome=label).inc(count)


@asynccontextmanager
async def chat_reconcile_tick():
    """reconcile_last_message_once 한 호출 처리 시간. drain 사이클은 worker_tick("reconcile") 이 측정."""
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started
        CHAT_RECONCILE_TICK_DURATION.observe(elapsed)


def chat_unread_recover_inc(result: str) -> None:
    label = result if result in CHAT_UNREAD_RECOVER_RESULTS else "other"
    CHAT_UNREAD_RECOVER_TOTAL.labels(result=label).inc()
