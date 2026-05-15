"""Mongo repository 메트릭.

op enum 은 화이트리스트 (find / find_one / insert / update / delete / aggregate / count + others).
collection 은 우리가 사용하는 9개 + 그 외 'other' (instrumentation/mongo 참조).
"""
from prometheus_client import Counter, Histogram


MONGO_OP_DURATION = Histogram(
    "mongo_op_duration_seconds",
    "Mongo repository operation duration.",
    labelnames=("op", "collection"),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0),
)

MONGO_OP_ERRORS_TOTAL = Counter(
    "mongo_op_errors_total",
    "Mongo repository operation errors grouped by exception class.",
    labelnames=("op", "collection", "exc_type"),
)
