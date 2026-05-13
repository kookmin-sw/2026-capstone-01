"""채팅 도메인 메트릭 — WebSocket / fan-out / reconcile / unread recover."""
from prometheus_client import Counter, Gauge, Histogram


# ────────────────────────────────────────────────────────────────────
# WebSocket
# ────────────────────────────────────────────────────────────────────

CHAT_WS_ACTIVE_CONNECTIONS = Gauge(
    "chat_ws_active_connections",
    "Currently connected WebSocket count by node.",
    labelnames=("node_id",),
)

CHAT_WS_CONNECT_TOTAL = Counter(
    "chat_ws_connect_total",
    "WebSocket connection attempts by result.",
    labelnames=("result",),
)

CHAT_WS_OP_TOTAL = Counter(
    "chat_ws_op_total",
    "WebSocket op count by op kind and result.",
    labelnames=("op", "result"),
)

CHAT_MESSAGE_SEND_DURATION = Histogram(
    "chat_message_send_duration_seconds",
    "Message send to fan-out completion latency, separated by fan-out path.",
    labelnames=("fanout_path",),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0),
)


# ────────────────────────────────────────────────────────────────────
# Fan-out publish / dispatch
# ────────────────────────────────────────────────────────────────────

CHAT_FANOUT_PUBLISH_TOTAL = Counter(
    "chat_fanout_publish_total",
    "Fan-out publish to Pub/Sub count by op.",
    labelnames=("op",),
)

CHAT_FANOUT_DISPATCH_TOTAL = Counter(
    "chat_fanout_dispatch_total",
    "Fan-out dispatcher delivery count by op and result.",
    labelnames=("op", "result"),
)

CHAT_FANOUT_DISPATCH_DURATION = Histogram(
    "chat_fanout_dispatch_duration_seconds",
    "Fan-out dispatcher per-envelope processing time.",
    labelnames=("op",),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0),
)

CHAT_ACTIVE_NODES = Gauge(
    "chat_active_nodes",
    "Active node count seen by node_registry. Updated each heartbeat tick.",
)

CHAT_NODE_HEARTBEAT_FAILURES = Counter(
    "chat_node_heartbeat_failures_total",
    "Node heartbeat failures.",
    labelnames=("node_id",),
)


# ────────────────────────────────────────────────────────────────────
# Reconcile / Unread recover
# ────────────────────────────────────────────────────────────────────

CHAT_RECONCILE_DIRTY_SET_SIZE = Gauge(
    "chat_reconcile_dirty_set_size",
    "dirty:chat_room SET cardinality measured at start of every tick (SCARD). Backlog signal.",
)

CHAT_RECONCILE_BATCH_POP_TOTAL = Counter(
    "chat_reconcile_batch_pop_total",
    "Reconcile batch pop attempts grouped by terminal result.",
    labelnames=("result",),
)

CHAT_RECONCILE_ROOMS_PROCESSED_TOTAL = Counter(
    "chat_reconcile_rooms_processed_total",
    "Per-room reconcile outcome count.",
    labelnames=("outcome",),
)

CHAT_RECONCILE_TICK_DURATION = Histogram(
    "chat_reconcile_tick_duration_seconds",
    "Single reconcile_last_message_once invocation duration.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

CHAT_UNREAD_RECOVER_TOTAL = Counter(
    "chat_unread_recover_total",
    "recover_unread_for_user terminal result count.",
    labelnames=("result",),
)
