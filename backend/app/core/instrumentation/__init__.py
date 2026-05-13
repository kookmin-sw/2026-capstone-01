"""워커 / 도메인 코드용 메트릭 instrumentation 패키지.

도메인 코드에 메트릭 코드를 직접 박지 않고 데코레이터 / 컨텍스트 매니저로 한 줄 부착
가능하도록 한다. 메트릭 정의 자체는 `app.core.metric` 에 모은다.

서브모듈:
  - worker        : worker_tick / withdraw_purge_run / prime_worker_gauges
  - chat          : WS / fan-out / reconcile / unread recover
  - fcm           : FCM multicast / 토큰 정리
  - ai            : inference / external_call / token usage / Gemini callback
  - db            : route / transaction / SQLAlchemy 이벤트 부착
  - redis_client  : Redis 명령 / Lua script
  - mongo         : measure_mongo_op 데코레이터
  - event_loop    : lag loop / asyncio tasks / pool gauge 폴링

외부에선 `from app.core.instrumentation import X` 형태로 그대로 접근한다.
"""
from app.core.instrumentation.ai import (
    AI_MODEL_NAMES,
    AI_PROVIDERS,
    AI_RESULTS,
    GeminiInstrumentationHandler,
    ai_external_call,
    ai_inference,
    ai_model_load_duration_set,
    ai_token_usage_inc,
)
from app.core.instrumentation.chat import (
    CHAT_RECONCILE_BATCH_RESULTS,
    CHAT_RECONCILE_OUTCOMES,
    CHAT_UNREAD_RECOVER_RESULTS,
    CHAT_WS_CONNECT_RESULTS,
    CHAT_WS_OP_RESULTS,
    chat_active_nodes_set,
    chat_fanout_dispatch,
    chat_fanout_dispatch_alive,
    chat_fanout_publish_inc,
    chat_message_send_timer,
    chat_node_heartbeat_failure,
    chat_reconcile_batch_pop_inc,
    chat_reconcile_dirty_set_size_set,
    chat_reconcile_rooms_processed_inc,
    chat_reconcile_tick,
    chat_unread_recover_inc,
    chat_ws_connect_result,
    chat_ws_connection_dec,
    chat_ws_connection_inc,
    chat_ws_op,
    chat_ws_op_validation_failure,
)
from app.core.instrumentation.db import (
    DB_TRANSACTION_RESULTS,
    attach_db_instrumentation,
    db_route_for_path,
    db_transaction_inc,
)
from app.core.instrumentation.event_loop import (
    start_event_loop_monitor,
    stop_event_loop_monitor,
)
from app.core.instrumentation.fcm import (
    FCM_MULTICAST_OUTCOMES,
    FCM_PATHS,
    FCM_SEND_RESULTS,
    fcm_multicast_devices_inc,
    fcm_multicast_timer,
    fcm_send_inc,
    fcm_token_purged_inc,
)
from app.core.instrumentation.mongo import (
    MONGO_COLLECTIONS,
    MONGO_OP_KINDS,
    measure_mongo_op,
)
from app.core.instrumentation.redis_client import (
    instrument_lua_script,
    instrument_redis_client,
)
from app.core.instrumentation.worker import (
    WORKER_NAMES,
    prime_worker_gauges,
    withdraw_purge_run,
    worker_tick,
)


__all__ = (
    # worker
    "WORKER_NAMES",
    "prime_worker_gauges",
    "withdraw_purge_run",
    "worker_tick",
    # chat
    "CHAT_RECONCILE_BATCH_RESULTS",
    "CHAT_RECONCILE_OUTCOMES",
    "CHAT_UNREAD_RECOVER_RESULTS",
    "CHAT_WS_CONNECT_RESULTS",
    "CHAT_WS_OP_RESULTS",
    "chat_active_nodes_set",
    "chat_fanout_dispatch",
    "chat_fanout_dispatch_alive",
    "chat_fanout_publish_inc",
    "chat_message_send_timer",
    "chat_node_heartbeat_failure",
    "chat_reconcile_batch_pop_inc",
    "chat_reconcile_dirty_set_size_set",
    "chat_reconcile_rooms_processed_inc",
    "chat_reconcile_tick",
    "chat_unread_recover_inc",
    "chat_ws_connect_result",
    "chat_ws_connection_dec",
    "chat_ws_connection_inc",
    "chat_ws_op",
    "chat_ws_op_validation_failure",
    # fcm
    "FCM_MULTICAST_OUTCOMES",
    "FCM_PATHS",
    "FCM_SEND_RESULTS",
    "fcm_multicast_devices_inc",
    "fcm_multicast_timer",
    "fcm_send_inc",
    "fcm_token_purged_inc",
    # ai
    "AI_MODEL_NAMES",
    "AI_PROVIDERS",
    "AI_RESULTS",
    "GeminiInstrumentationHandler",
    "ai_external_call",
    "ai_inference",
    "ai_model_load_duration_set",
    "ai_token_usage_inc",
    # db
    "DB_TRANSACTION_RESULTS",
    "attach_db_instrumentation",
    "db_route_for_path",
    "db_transaction_inc",
    # redis
    "instrument_lua_script",
    "instrument_redis_client",
    # mongo
    "MONGO_COLLECTIONS",
    "MONGO_OP_KINDS",
    "measure_mongo_op",
    # event loop
    "start_event_loop_monitor",
    "stop_event_loop_monitor",
)
