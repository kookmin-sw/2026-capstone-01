"""Mongo repository 메서드용 데코레이터.

op / collection 라벨은 데코레이션 시점 1회만 화이트리스트 정규화 → wrapper 호출 비용 0.
"""
import time
from functools import wraps

from app.core.metric import (
    MONGO_OP_DURATION,
    MONGO_OP_ERRORS_TOTAL,
)


MONGO_OP_KINDS = (
    "find", "find_one", "insert", "update", "delete",
    "aggregate", "count", "replace", "save", "other",
)

# beanie 컬렉션 + motor 네이티브 chat_message + 'other'.
MONGO_COLLECTIONS = (
    "withdrawal_request", "tripmate_post_draft", "tripmate_search_history",
    "tripmate_image", "place", "tour_search_history",
    "friend_search_history", "inbox", "chat_message", "other",
)


def measure_mongo_op(op: str, collection: str):
    """Mongo repository 메서드 데코레이터 — duration + 예외 카운트 자동 부착.

    라벨은 화이트리스트 외 입력이면 'other' 로 통합 — 카디널리티 누수 차단.

    사용 예:
        @measure_mongo_op("find", "withdrawal_request")
        async def find_due(self, now): ...
    """
    op_label = op if op in MONGO_OP_KINDS else "other"
    collection_label = collection if collection in MONGO_COLLECTIONS else "other"

    def deco(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            started = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                MONGO_OP_ERRORS_TOTAL.labels(
                    op=op_label, collection=collection_label, exc_type=type(exc).__name__,
                ).inc()
                raise
            finally:
                elapsed = time.perf_counter() - started
                MONGO_OP_DURATION.labels(op=op_label, collection=collection_label).observe(elapsed)

        return wrapper
    return deco
