"""Mongo repository 메서드용 데코레이터.

op / collection 라벨은 데코레이션 시점에 화이트리스트로 정규화되어 wrapper 호출 비용 0.
"""
import time
from functools import wraps

from app.core.metric import (
    MONGO_OP_DURATION,
    MONGO_OP_ERRORS_TOTAL,
)


# op enum (Mongo 동작 단위).
MONGO_OP_KINDS = (
    "find", "find_one", "insert", "update", "delete",
    "aggregate", "count", "replace", "save", "other",
)

# collection enum (init_beanie 7 + motor 네이티브 chat_message + 그 외 'other').
MONGO_COLLECTIONS = (
    "withdrawal_request", "tripmate_post_draft", "tripmate_search_history",
    "tripmate_image", "place", "tour_search_history",
    "friend_search_history", "inbox", "chat_message", "other",
)


def measure_mongo_op(op: str, collection: str):
    """Mongo repository 메서드 데코레이터.

    op 와 collection 라벨로 mongo_op_duration_seconds + mongo_op_errors_total 자동 관측.
    예외는 result enum 분리 없이 exc_type 라벨로 분류 — Counter 가 자동 raise propagate.

    op / collection 라벨은 데코레이션 시점에 화이트리스트 (MONGO_OP_KINDS /
    MONGO_COLLECTIONS) 로 정규화 — 오타나 enum 미반영 호출이 들어와도 'other' 로
    통합되어 라벨 카디널리티 누수 차단. 정규화는 모듈 import 시 1회만 수행되어
    wrapper 호출 비용 0.

    사용 예:
        @measure_mongo_op("find", "withdrawal_request")
        async def find_due(self, now): ...

    PR 머지 게이트 (부착 누락 검증):
        git grep -nE 'async def [a-z]' app/domain/{auth,notification,...}/repository \
          | grep -v measure_mongo_op
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
