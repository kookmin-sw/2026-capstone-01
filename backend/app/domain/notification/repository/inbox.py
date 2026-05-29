"""인박스 컬렉션 리포지토리.

읽기는 beanie, 쓰기 / atomic update / cascade 는 motor native — query 1회 + race-free.

권한 검증은 query 안에 `recipient_id` 를 포함해 atomic 처리 (타인 항목은 매칭 실패 → modified=0).
"""
from typing import Optional
from datetime import datetime, timezone
from beanie import PydanticObjectId

from app.domain.notification.model.inbox import InboxItem
from app.core.instrumentation import measure_mongo_op


PAGE_SIZE = 20
UNREAD_COUNT_CAP = 999


class InboxRepository:
    """thin wrapper. RDB session 의존 없어 호출당 인스턴스 비용 0."""

    @measure_mongo_op("insert", "inbox")
    async def insert(self, item: InboxItem) -> InboxItem:
        """`uq_inbox_dedup` 충돌 시 DuplicateKeyError 그대로 propagate — service 가 멱등 처리."""
        await item.insert()
        return item


    @measure_mongo_op("find", "inbox")
    async def find_by_recipient(
        self,
        recipient_id: str,
        cursor: Optional[datetime] = None,
        limit: int = PAGE_SIZE,
    ) -> list[InboxItem]:
        """display=true 최신순. `limit+1` fetch 로 has_more 판정.

        tie-break 은 `_id` desc 보조 정렬 — 같은 ms 항목 누락 위험을 실용적으로 무시.
        """
        query = InboxItem.find(
            InboxItem.recipient_id == recipient_id,
            InboxItem.display == True,
        )
        if cursor is not None:
            query = query.find(InboxItem.created_at < cursor)
        return await query.sort("-created_at", "-_id").limit(limit + 1).to_list()


    @measure_mongo_op("count", "inbox")
    async def count_unread(self, recipient_id: str, cap: int = UNREAD_COUNT_CAP) -> int:
        """미읽음 (display=true AND read_at=null) 카운트. `limit=cap+1` 로 cap 까지만 셈."""
        coll = InboxItem.get_motor_collection()
        return await coll.count_documents(
            {"recipient_id": recipient_id, "display": True, "read_at": None},
            limit=cap + 1,
        )


    @measure_mongo_op("update", "inbox")
    async def hide(self, inbox_item_id: PydanticObjectId, recipient_id: str) -> bool:
        """X 버튼. 권한 검증을 query 에 포함해 atomic. 매칭 실패면 False (service 가 404 매핑)."""
        coll = InboxItem.get_motor_collection()
        res = await coll.update_one(
            {"_id": inbox_item_id, "recipient_id": recipient_id, "display": True},
            {"$set": {"display": False}},
        )
        return res.modified_count == 1


    @measure_mongo_op("update", "inbox")
    async def mark_all_read(self, recipient_id: str) -> int:
        """미읽음 일괄 read 처리. display=true AND read_at=null 만 대상 (멱등)."""
        coll = InboxItem.get_motor_collection()
        res = await coll.update_many(
            {"recipient_id": recipient_id, "display": True, "read_at": None},
            {"$set": {"read_at": datetime.now(timezone.utc)}},
        )
        return res.modified_count


    @measure_mongo_op("update", "inbox")
    async def hide_by_target(self, target_type: str, target_id: str) -> int:
        """게시글 삭제 cascade — `(target_type, target_id)` soft hide. `display=true` 만 대상 (멱등).

        `(target_type, target_id)` 는 인덱스 prefix 가 아니라 collection scan — 게시글 삭제 빈도가
        낮고 best-effort 라 수용. 컬렉션 크기가 임계치 넘으면 인덱스 추가 검토.
        """
        coll = InboxItem.get_motor_collection()
        res = await coll.update_many(
            {"target_type": target_type, "target_id": target_id, "display": True},
            {"$set": {"display": False}},
        )
        return res.modified_count


    @measure_mongo_op("delete", "inbox")
    async def delete_by_user(self, user_id: str) -> int:
        """유저 탈퇴 cascade — recipient/actor 매칭 hard delete."""
        coll = InboxItem.get_motor_collection()
        res = await coll.delete_many({
            "$or": [{"recipient_id": user_id}, {"actor_id": user_id}],
        })
        return res.deleted_count
