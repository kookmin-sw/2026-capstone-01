"""Prometheus 메트릭 정의 패키지.

라벨 정책:
  - 고유 ID(user_id, room_id, session_id, request_id)는 라벨로 쓰지 않는다.
  - 결과 enum 라벨에는 'other' catch-all 을 둔다.
  - env 라벨은 Prometheus external_labels 로 부여하며 앱에서는 명시하지 않는다.

서브모듈은 instrumentation 패키지와 1:1 매핑:
  - auth          : AUTH_FAILURES + AUTH_KINDS enum
  - worker        : WORKER_* / WITHDRAW_PURGE_*
  - chat          : CHAT_WS_* / CHAT_FANOUT_* / CHAT_RECONCILE_* / CHAT_UNREAD_*
  - fcm           : FCM_*
  - ai            : AI_*
  - db            : DB_*
  - redis_client  : REDIS_*
  - mongo         : MONGO_*
  - event_loop    : PYTHON_EVENT_LOOP_LAG / PYTHON_ASYNCIO_TASKS
  - fastapi       : build_instrumentator + DEEP_CANARY_DURATION

외부에서는 `from app.core.metric import X` 형태로 그대로 접근한다.
"""
from app.core.metric.worker import (
    WITHDRAW_PURGE_LAST_RUN_DURATION,
    WORKER_LAST_TICK_TIMESTAMP,
    WORKER_TICK_DURATION,
    WORKER_TICK_TOTAL,
)
from app.core.metric.redis_client import (
    REDIS_COMMAND_DURATION,
    REDIS_COMMAND_ERRORS_TOTAL,
    REDIS_LUA_SCRIPT_RUN_TOTAL,
)
from app.core.metric.mongo import (
    MONGO_OP_DURATION,
    MONGO_OP_ERRORS_TOTAL,
)
from app.core.metric.fcm import (
    FCM_MULTICAST_DEVICES_TOTAL,
    FCM_MULTICAST_DURATION,
    FCM_SEND_TOTAL,
    FCM_TOKEN_PURGED_TOTAL,
)
from app.core.metric.fastapi import (
    DEEP_CANARY_DURATION,
    build_instrumentator,
)
from app.core.metric.event_loop import (
    PYTHON_ASYNCIO_TASKS,
    PYTHON_EVENT_LOOP_LAG,
)
from app.core.metric.db import (
    DB_POOL_CHECKED_OUT,
    DB_POOL_SIZE,
    DB_QUERY_DURATION,
    DB_TRANSACTION_TOTAL,
)
from app.core.metric.chat import (
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
)
from app.core.metric.auth import (
    AUTH_FAILURES,
    AUTH_KINDS,
)
from app.core.metric.ai import (
    AI_EXTERNAL_CALL_DURATION,
    AI_EXTERNAL_CALL_TOTAL,
    AI_INFERENCE_DURATION,
    AI_INFERENCE_TOTAL,
    AI_MODEL_LOAD_DURATION,
    AI_TOKEN_USAGE_TOTAL,
)


__all__ = (
    # auth
    "AUTH_FAILURES",
    "AUTH_KINDS",
    # worker
    "WITHDRAW_PURGE_LAST_RUN_DURATION",
    "WORKER_LAST_TICK_TIMESTAMP",
    "WORKER_TICK_DURATION",
    "WORKER_TICK_TOTAL",
    # chat
    "CHAT_ACTIVE_NODES",
    "CHAT_FANOUT_DISPATCH_DURATION",
    "CHAT_FANOUT_DISPATCH_TOTAL",
    "CHAT_FANOUT_PUBLISH_TOTAL",
    "CHAT_MESSAGE_SEND_DURATION",
    "CHAT_NODE_HEARTBEAT_FAILURES",
    "CHAT_RECONCILE_BATCH_POP_TOTAL",
    "CHAT_RECONCILE_DIRTY_SET_SIZE",
    "CHAT_RECONCILE_ROOMS_PROCESSED_TOTAL",
    "CHAT_RECONCILE_TICK_DURATION",
    "CHAT_UNREAD_RECOVER_TOTAL",
    "CHAT_WS_ACTIVE_CONNECTIONS",
    "CHAT_WS_CONNECT_TOTAL",
    "CHAT_WS_OP_TOTAL",
    # fcm
    "FCM_MULTICAST_DEVICES_TOTAL",
    "FCM_MULTICAST_DURATION",
    "FCM_SEND_TOTAL",
    "FCM_TOKEN_PURGED_TOTAL",
    # ai
    "AI_EXTERNAL_CALL_DURATION",
    "AI_EXTERNAL_CALL_TOTAL",
    "AI_INFERENCE_DURATION",
    "AI_INFERENCE_TOTAL",
    "AI_MODEL_LOAD_DURATION",
    "AI_TOKEN_USAGE_TOTAL",
    # db
    "DB_POOL_CHECKED_OUT",
    "DB_POOL_SIZE",
    "DB_QUERY_DURATION",
    "DB_TRANSACTION_TOTAL",
    # redis
    "REDIS_COMMAND_DURATION",
    "REDIS_COMMAND_ERRORS_TOTAL",
    "REDIS_LUA_SCRIPT_RUN_TOTAL",
    # mongo
    "MONGO_OP_DURATION",
    "MONGO_OP_ERRORS_TOTAL",
    # event loop
    "PYTHON_ASYNCIO_TASKS",
    "PYTHON_EVENT_LOOP_LAG",
    # fastapi
    "DEEP_CANARY_DURATION",
    "build_instrumentator",
)
