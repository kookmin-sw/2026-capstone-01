"""RDB 메트릭 — query duration / 트랜잭션 outcome / 풀 gauge.

route 라벨은 도메인 단위 enum (chat / auth / tour / ... / health / other) 로 통제.
endpoint 별로 두지 않아 카디널리티 폭증을 차단한다.
"""
from prometheus_client import Counter, Gauge, Histogram


DB_QUERY_DURATION = Histogram(
    "db_query_duration_seconds",
    "Single SQL query execution duration grouped by domain route.",
    labelnames=("route",),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0),
)

DB_TRANSACTION_TOTAL = Counter(
    "db_transaction_total",
    "UnitOfWork transaction outcome count.",
    labelnames=("route", "result"),
)

DB_POOL_CHECKED_OUT = Gauge(
    "db_pool_checked_out",
    "Connections currently checked out from the SQLAlchemy pool.",
)

DB_POOL_SIZE = Gauge(
    "db_pool_size",
    "Configured size of the SQLAlchemy pool.",
)
