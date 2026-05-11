"""Chat 도메인 instrumentation — WS / fan-out / reconcile / unread.

WS 연결·op, fan-out publish/dispatch, reconcile drain, unread recover 등 채팅 도메인
전반의 메트릭 부착 헬퍼를 모은다. 모든 라벨은 화이트리스트 정규화로 카디널리티 누수를
차단한다.
"""
import time
from contextlib import asynccontextmanager

from app.config.setting import settings
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


# ────────────────────────────────────────────────────────────────────
# WS 연결 / op
# ────────────────────────────────────────────────────────────────────

# WS 연결 결과 enum. ws.py 의 4 분기에 매핑된다.
CHAT_WS_CONNECT_RESULTS = ("ok", "origin_denied", "auth_expired", "session_failed", "other")

# WS op 결과 enum. _classify_ws_op_error 와 일치.
CHAT_WS_OP_RESULTS = ("ok", "permission_denied", "validation", "not_found", "upstream", "other")
_KNOWN_WS_OP_RESULTS = frozenset(CHAT_WS_OP_RESULTS)

# WS op 라벨 화이트리스트. ClientRequest discriminated union 의 3 종.
# 악성 클라가 임의 op 문자열을 보내도 'other' 로 통합 — 카디널리티 폭발 차단.
_KNOWN_WS_OPS = frozenset({"send", "refresh", "read"})


def _normalize_ws_op(op) -> str:
    """검증 전 raw op 입력을 라벨로 안전하게 정규화."""
    if isinstance(op, str) and op in _KNOWN_WS_OPS:
        return op
    return "other"


def chat_ws_connect_result(result: str) -> None:
    """WS 연결 시도 결과 카운트. ws.py 의 4 close-code 분기에서 호출.

    result 라벨은 CHAT_WS_CONNECT_RESULTS 화이트리스트 통과 — ws.py 분기 추가 누락 /
    오타로 인한 카디널리티 누수 차단.
    """
    label = result if result in CHAT_WS_CONNECT_RESULTS else "other"
    CHAT_WS_CONNECT_TOTAL.labels(result=label).inc()


def chat_ws_connection_inc() -> None:
    """WS accept 직후 호출. 활성 연결 +1."""
    CHAT_WS_ACTIVE_CONNECTIONS.labels(node_id=settings.NODE_ID).inc()


def chat_ws_connection_dec() -> None:
    """WS finally 블록에서 호출. 활성 연결 -1."""
    CHAT_WS_ACTIVE_CONNECTIONS.labels(node_id=settings.NODE_ID).dec()


def _classify_ws_op_error(exc: BaseException) -> str:
    """예외를 result 라벨 enum 으로 매핑.

    분기 우선순위 (specific → general):
      1. `exc.error_kind` — 도메인 커스텀 예외가 self-classify (rename 안전, IoC).
         ChatRoomNotFoundError 같이 ValueError subclass 인 도메인 예외를 isinstance 보다
         먼저 잡아야 'validation' 으로 잘못 분류되지 않는다.
      2. `isinstance(PermissionError)` — Python builtin (속성 부여 불가).
      3. `isinstance(ValueError)` — pydantic v2 ValidationError 도 ValueError subclass 라
         한 번에 처리. domain ChatRoomNotFoundError 는 step 1 에서 이미 catch 됐으므로
         여기엔 일반 ValueError 만 도달.
      4. 'other' — catch-all.

    반환값은 _KNOWN_WS_OP_RESULTS 화이트리스트 통과 — 도메인이 enum 외 error_kind 를
    박아도 'other' 로 통합되어 카디널리티 누수 차단.
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
    """WS op 1 건의 결과 카운트.

    op 라벨은 _normalize_ws_op 로 화이트리스트 통과 — 악성 클라의 임의 op 문자열로 인한
    카디널리티 폭발 차단.
    예외는 result 라벨로 분류 후 그대로 raise — 호출 측이 send_json 으로 클라에 변환 응답한다.
    """
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
    """파싱 단계 (Pydantic ValidationError) 에서 호출. raw op 키도 화이트리스트 통과."""
    CHAT_WS_OP_TOTAL.labels(op=_normalize_ws_op(op_label), result="validation").inc()


@asynccontextmanager
async def chat_message_send_timer(fanout_path: str):
    """메시지 송신 -> fan-out 까지 latency. fanout_path: local | cross_node."""
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started
        CHAT_MESSAGE_SEND_DURATION.labels(fanout_path=fanout_path).observe(elapsed)


# ────────────────────────────────────────────────────────────────────
# Fan-out publish / dispatch
# ────────────────────────────────────────────────────────────────────

# fan-out envelope op enum — publish 와 dispatch 양쪽이 공유. dispatch 는 다른 노드의
# envelope 도 받아 노드 버전 혼재 / 악성 envelope 에서 unknown op 가능 → 'other' 통합.
_KNOWN_FANOUT_OPS = frozenset({"room", "user", "session", "subscribe", "unsubscribe"})


def _normalize_fanout_op(op) -> str:
    """fan-out op 라벨을 화이트리스트로 정규화."""
    if isinstance(op, str) and op in _KNOWN_FANOUT_OPS:
        return op
    return "other"


def chat_fanout_publish_inc(op: str) -> None:
    """publish 1 건 카운트. op enum: room | user | session | subscribe | unsubscribe."""
    CHAT_FANOUT_PUBLISH_TOTAL.labels(op=_normalize_fanout_op(op)).inc()


def chat_fanout_dispatch_alive() -> None:
    """polling iteration 마다 last_tick_timestamp 만 갱신.

    _dispatch_loop 가 envelope 0 건이어도 liveness 신호를 유지한다.
    chat_fanout_dispatch context 와 별도 — context 는 envelope 처리 시간 / 결과 측정,
    이 함수는 순수 liveness (idle 한 dispatcher 도 살아있음을 알린다).
    """
    WORKER_LAST_TICK_TIMESTAMP.labels(
        worker="fanout_dispatch", node_id=settings.NODE_ID,
    ).set(time.time())


@asynccontextmanager
async def chat_fanout_dispatch(op: str):
    """디스패처가 envelope 1 건 처리하는 시간 + 결과 측정.

    예외는 result=other 로 카운트 후 그대로 raise 한다 (worker_tick 이 다시 잡아 swallow).
    op 라벨은 _normalize_fanout_op 로 통과 — 다른 노드의 unknown / 악성 envelope 보호.
    """
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
    """node_registry heartbeat tick 안에서 호출. ZSET 의 활성 노드 수를 그대로 set."""
    CHAT_ACTIVE_NODES.set(value)


def chat_node_heartbeat_failure() -> None:
    """heartbeat 예외 분기에서 호출."""
    CHAT_NODE_HEARTBEAT_FAILURES.labels(node_id=settings.NODE_ID).inc()


# ────────────────────────────────────────────────────────────────────
# Reconcile / Unread recover
# ────────────────────────────────────────────────────────────────────

# batch_pop result enum:
#   - empty : SET 이 비어 있어 pop 결과 0건
#   - ok    : Mongo aggregate + RDB commit 모두 성공 (partial UPDATE 실패는 ok 안에서 outcome=failed 로 분리)
#   - mongo_failed : Mongo aggregate 실패 → 배치 통째로 재적재
#   - rdb_failed   : commit 실패 → 배치 통째로 재적재
#   - other        : catch-all (N-10)
CHAT_RECONCILE_BATCH_RESULTS = ("empty", "ok", "mongo_failed", "rdb_failed", "other")

# rooms_processed outcome enum:
#   - updated : RDB UPDATE 성공
#   - skipped : Mongo hit 0 (방 생성 직후 삭제 등)
#   - failed  : 단일 방 UPDATE 실패 → 그 방만 재적재 (partial)
CHAT_RECONCILE_OUTCOMES = ("updated", "skipped", "failed")

# unread_recover result enum (recover_unread_for_user 의 4 종착점):
#   - ok             : 정상 종료 (활성 방 없음 또는 counts 반영 완료)
#   - redis_failed   : pipeline 실패 후 DEL 로 정리 — partial state 차단 성공
#   - cleanup_failed : DEL 도 실패 — partial state 잔존 (운영 관측 필요)
#   - other          : catch-all
CHAT_UNREAD_RECOVER_RESULTS = ("ok", "redis_failed", "cleanup_failed", "other")


def chat_reconcile_dirty_set_size_set(value: int) -> None:
    """매 tick 시작 시 SCARD dirty:chat_room 결과 그대로 set."""
    CHAT_RECONCILE_DIRTY_SET_SIZE.set(value)


def chat_reconcile_batch_pop_inc(result: str) -> None:
    """result 라벨은 CHAT_RECONCILE_BATCH_RESULTS 화이트리스트 통과 — 누수 차단."""
    label = result if result in CHAT_RECONCILE_BATCH_RESULTS else "other"
    CHAT_RECONCILE_BATCH_POP_TOTAL.labels(result=label).inc()


def chat_reconcile_rooms_processed_inc(outcome: str, count: int = 1) -> None:
    """count > 0 일 때만 카운트. 0 이면 no-op (의미 없는 시리즈 등록 방지).

    outcome 라벨은 CHAT_RECONCILE_OUTCOMES 화이트리스트 통과 — 누수 차단.
    """
    if count <= 0:
        return
    label = outcome if outcome in CHAT_RECONCILE_OUTCOMES else "other"
    CHAT_RECONCILE_ROOMS_PROCESSED_TOTAL.labels(outcome=label).inc(count)


@asynccontextmanager
async def chat_reconcile_tick():
    """reconcile_last_message_once 한 호출의 처리 시간 측정.

    drain 사이클 단위 시간은 worker_tick("reconcile") 이 따로 측정한다.
    """
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started
        CHAT_RECONCILE_TICK_DURATION.observe(elapsed)


def chat_unread_recover_inc(result: str) -> None:
    """result 라벨은 CHAT_UNREAD_RECOVER_RESULTS 화이트리스트 통과 — 누수 차단."""
    label = result if result in CHAT_UNREAD_RECOVER_RESULTS else "other"
    CHAT_UNREAD_RECOVER_TOTAL.labels(result=label).inc()
