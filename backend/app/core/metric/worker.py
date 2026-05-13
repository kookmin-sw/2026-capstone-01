"""워커 4종 tick liveness / 결과 / 시간 메트릭.

reconcile · node_heartbeat · fanout_dispatch · withdraw_purge 의 단일 라벨 체계.
withdraw_purge 는 일일 1 회 — Histogram 대신 Gauge 로 마지막 사이클 duration 만 박는다.
"""
from prometheus_client import Counter, Gauge, Histogram


# 4 종 워커 (reconcile, node_heartbeat, fanout_dispatch, withdraw_purge) 의 tick 관측.
WORKER_LAST_TICK_TIMESTAMP = Gauge(
    "worker_last_tick_timestamp",
    "Last tick wall-clock timestamp (seconds since epoch). WorkerStale alert source.",
    labelnames=("worker", "node_id"),
)

WORKER_TICK_TOTAL = Counter(
    "worker_tick_total",
    "Worker tick count by result.",
    labelnames=("worker", "node_id", "result"),
)

WORKER_TICK_DURATION = Histogram(
    "worker_tick_duration_seconds",
    "Worker tick duration. Excludes withdraw_purge (daily — Gauge instead).",
    labelnames=("worker", "node_id"),
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 30.0, 300.0),
)

WITHDRAW_PURGE_LAST_RUN_DURATION = Gauge(
    "withdraw_purge_last_run_duration_seconds",
    "Last withdraw_purge cycle duration. Daily — Histogram is meaningless.",
    labelnames=("node_id",),
)
