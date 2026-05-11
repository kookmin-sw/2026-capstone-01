"""인박스 컬렉션 리포지토리 — beanie + motor 네이티브 mix.

읽기는 beanie ORM (`InboxItem.find(...)`), 쓰기 / atomic update / cascade delete 는
`InboxItem.get_motor_collection()` 으로 raw motor 를 사용해 query 1회 + race-free 처리.

쿼리 전략:
    - 인박스 페이지네이션: 인덱스 `ix_inbox_recipient_display_created` 가
      `{recipient_id, display, created_at DESC}` 컴파운드라 한 번에 커버. tie-break 은 `_id`
      보조 정렬 — 같은 ms 항목 누락 위험을 실용적으로 무시.
    - 미읽음 카운트: 위 인덱스 prefix `{recipient_id, display}` 로 커버 (read_at 추가 필터).
      cap 으로 999+ 표시 지원 — `count_documents(limit=cap+1)`.
    - hide / mark_read: query 에 `recipient_id` 포함해 atomic 권한 검증. 다른 유저 항목에
      대한 modify 시도는 매칭 실패 → modified_count=0.
    - cascade delete: 유저 탈퇴 시만 hard delete (recipient/actor 매칭). 게시물/댓글 삭제는
      cascade 안 함 — 좋아요 취소 항목 보존 정책과 대칭, stale 은 TTL 30일로 자연 정리.
"""
from typing import Optional
from datetime import datetime, timezone
from beanie import PydanticObjectId

from app.domain.notification.model.inbox import InboxItem
from app.core.instrumentation import measure_mongo_op


# 인박스 페이지 크기 — 모바일 한 화면에 fit.
PAGE_SIZE = 20

# 미읽음 카운트 상한 — 999+ 표시용.
UNREAD_COUNT_CAP = 999


class InboxRepository:
    """인박스 컬렉션 thin wrapper. beanie Document 위에서 동작.

    RDB session 의존 없음 — Mongo 단독. service 가 호출당 인스턴스 새로 만들어도 비용 0.
    """

    # ──────────────────── Create ────────────────────

    @measure_mongo_op("insert", "inbox")
    async def insert(self, item: InboxItem) -> InboxItem:
        """인박스 항목 1건 insert.

        `uq_inbox_dedup` UNIQUE 인덱스 충돌 시 `pymongo.errors.DuplicateKeyError`
        가 그대로 propagate — service 가 catch 해서 멱등 처리. partial filter (`display: true`)
        X 로 숨겼던 경우는 충돌 안 하고 새 항목으로 들어감.
        """
        await item.insert()
        return item


    # ──────────────────── Read (목록 — 커서 페이지네이션) ────────────────────

    @measure_mongo_op("find", "inbox")
    async def find_by_recipient(
        self,
        recipient_id: str,
        cursor: Optional[datetime] = None,
        limit: int = PAGE_SIZE,
    ) -> list[InboxItem]:
        """인박스 페이지네이션 — `display=True`, 최신순.

        `limit + 1` fetch 로 has_more 판정 — service 단에서 `[:limit]` 로 잘라 반환.
        같은 ms 항목 tie-break 은 `_id` desc 보조 정렬로 흡수 — 정확한 (created_at, _id)
        튜플 비교는 생략 (실용상 같은 ms 충돌 거의 없음, UX 영향 미미).
        """
        query = InboxItem.find(
            InboxItem.recipient_id == recipient_id,
            InboxItem.display == True,
        )
        if cursor is not None:
            query = query.find(InboxItem.created_at < cursor)
        return await query.sort("-created_at", "-_id").limit(limit + 1).to_list()


    # ──────────────────── Read (미읽음 카운트) ────────────────────

    @measure_mongo_op("count", "inbox")
    async def count_unread(self, recipient_id: str, cap: int = UNREAD_COUNT_CAP) -> int:
        """미읽음 항목 카운트 — `display=true AND read_at=null`.

        `count_documents(limit=cap+1)` — cap 보다 많아도 cap+1 까지만 셈. 호출자가
        `min(count, cap)` 적용 후 응답 (chat unread 패턴과 일관).
        """
        coll = InboxItem.get_motor_collection()
        return await coll.count_documents(
            {"recipient_id": recipient_id, "display": True, "read_at": None},
            limit=cap + 1,
        )


    # ──────────────────── Update (X 버튼 / 읽음 처리) ────────────────────

    @measure_mongo_op("update", "inbox")
    async def hide(self, inbox_item_id: PydanticObjectId, recipient_id: str) -> bool:
        """X 버튼 — `display=False` 토글. 본인 소유 검증을 query 안에 포함 (atomic).

        Returns:
            True  — 1 row modified
            False — id 미존재 / 다른 유저 소유 / 이미 display=false. service 가 NotFound 매핑.
        """
        coll = InboxItem.get_motor_collection()
        res = await coll.update_one(
            {"_id": inbox_item_id, "recipient_id": recipient_id, "display": True},
            {"$set": {"display": False}},
        )
        return res.modified_count == 1


    @measure_mongo_op("update", "inbox")
    async def mark_all_read(self, recipient_id: str) -> int:
        """인박스 진입 시 미읽음 일괄 읽음 처리. 변경된 row 수 반환.

        대상은 `display=true AND read_at=null` 만 — 이미 읽었거나 숨긴 항목은 건드리지 않음.
        멱등 (이미 모두 읽었으면 0).
        """
        coll = InboxItem.get_motor_collection()
        res = await coll.update_many(
            {"recipient_id": recipient_id, "display": True, "read_at": None},
            {"$set": {"read_at": datetime.now(timezone.utc)}},
        )
        return res.modified_count


    # ──────────────────── Cascade (유저 탈퇴만) ────────────────────

    @measure_mongo_op("delete", "inbox")
    async def delete_by_user(self, user_id: str) -> int:
        """유저 탈퇴 cascade — recipient 또는 actor 매칭 항목 일괄 hard delete.

        `recipient_id` 는 페이지네이션 인덱스 prefix, `actor_id` 는 단독 인덱스로 커버.
        """
        coll = InboxItem.get_motor_collection()
        res = await coll.delete_many({
            "$or": [{"recipient_id": user_id}, {"actor_id": user_id}],
        })
        return res.deleted_count
