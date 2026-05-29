"""InboxItem 컬렉션 e2e 통합 테스트 (실 Mongo).

unit 테스트가 mock 으로 검증할 수 없는 영역을 cover:
    - `uq_inbox_dedup` partial unique 인덱스가 실 Mongo 에 적용되어 동작
    - `display=true` 조건 partial filter 가 정확히 작동 (X 후 새 항목 가능)
    - atomic update (`hide` / `mark_all_read`) 가 race-free
    - cascade `delete_by_user` 의 `$or` 매칭

검증 매트릭스:

    | 시나리오                                | 기대                                    |
    |---|---|
    | insert + list (display=true)            | 응답에 보임                              |
    | 같은 (recipient, actor, type, target)   | DuplicateKeyError (partial unique 충돌) |
    | 첫 항목 hide → 같은 키 새 insert        | 성공 (display=false 는 인덱스 밖)       |
    | mark_all_read=True 후 read_at 채워짐    | DB read_at != null                      |
    | 응답 dto.is_read 는 mark 전 상태        | False (인스타 패턴)                      |
    | hide 후 list 에서 제외                  | response 에 안 나옴                     |
    | count_unread (display=true & null)      | 정확한 카운트 (cap 999)                  |
    | cascade_user_withdrawn (recipient/actor)| 양쪽 매칭 모두 삭제                      |
"""
import pytest
from pymongo.errors import DuplicateKeyError
from beanie import PydanticObjectId

from app.domain.notification.service.exception import InboxItemNotFoundError
from app.domain.notification.repository.inbox import InboxRepository
from app.domain.notification.model.inbox import (
    InboxItem,
    InboxItemType,
    TargetType,
)


pytestmark = pytest.mark.integration


def _make_inbox_item(
    *,
    recipient_id: str = "USER_recipient",
    actor_id: str = "USER_actor",
    type: InboxItemType = InboxItemType.FEED_LIKE,
    target_id: str = "FDP_x",
    comment_id: str | None = None,
    actor_name: str = "actorName",
) -> InboxItem:
    """test 용 InboxItem 인스턴스 — 실 mongo 에 insert 가능한 minimal 형태."""
    return InboxItem(
        recipient_id=recipient_id,
        actor_id=actor_id,
        type=type,
        target_type=TargetType.FEED_POST if type != InboxItemType.TRIPMATE_LIKE else TargetType.TRIPMATE_POST,
        target_id=target_id,
        comment_id=comment_id,
        actor_name=actor_name,
    )


# ──────────────────── partial unique 인덱스 ────────────────────

class TestPartialUniqueIndex:
    """`uq_inbox_dedup` 인덱스가 실 mongo 에 적용되어 의도대로 동작하는지.

    좋아요 취소→재좋아요 시 항목 폭증 방지의 핵심 가드. unit 은 mock 이라 인덱스 자체를
    검증 못 함 — 통합으로만 보장 가능.
    """

    async def test_duplicate_active_item_raises(self, mongo_db):
        """display=true 인 같은 (recipient, actor, type, target, null comment) 조합 → 충돌."""
        repo = InboxRepository()

        await repo.insert(_make_inbox_item())

        with pytest.raises(DuplicateKeyError):
            await repo.insert(_make_inbox_item())


    async def test_hide_then_reinsert_succeeds(self, mongo_db, inbox_service):
        """X 로 숨긴(display=false) 항목은 partial filter 밖 → 같은 키 새 insert 가능.

        Q1 결정: "X 후 같은 사람이 다시 좋아요 → 새 항목 OK". 실 인덱스로 보장.
        """
        repo = InboxRepository()
        first = _make_inbox_item()
        await repo.insert(first)

        # X 버튼 — display=false
        await inbox_service.hide_item(
            recipient_id="USER_recipient",
            inbox_item_id=str(first.id),
        )

        # 같은 키 새 항목 — partial filter 에서 첫 번째 빠짐 → 성공
        second = _make_inbox_item()
        await repo.insert(second)

        # 둘 다 DB 에 존재 (display=false + display=true)
        coll = InboxItem.get_motor_collection()
        assert await coll.count_documents({"recipient_id": "USER_recipient"}) == 2


    async def test_different_comment_ids_dont_conflict(self, mongo_db):
        """COMMENT 항목은 comment_id 가 매번 달라 자연 unique."""
        repo = InboxRepository()

        await repo.insert(_make_inbox_item(
            type=InboxItemType.FEED_COMMENT, comment_id="CMT_1",
        ))
        # raise 없이 정상 — 다른 comment_id
        await repo.insert(_make_inbox_item(
            type=InboxItemType.FEED_COMMENT, comment_id="CMT_2",
        ))


# ──────────────────── list_items + 자동 읽음 처리 ────────────────────

class TestListInboxFlow:
    """인박스 e2e — 페이지네이션 + 자동 mark_as_read 의 atomic update."""

    async def test_list_returns_inserted_in_reverse_chronological(
        self, mongo_db, inbox_service,
    ):
        """insert 순서대로 → list 는 최신순 (reverse)."""
        repo = InboxRepository()
        for i in range(3):
            await repo.insert(_make_inbox_item(
                target_id=f"FDP_{i}", actor_id=f"USER_a_{i}",
            ))

        result = await inbox_service.list_items(
            recipient_id="USER_recipient",
        )

        assert len(result.items) == 3
        # 최신순 — 마지막에 insert 한 게 첫 번째
        assert result.items[0].target_id == "FDP_2"
        assert result.items[2].target_id == "FDP_0"


    async def test_mark_as_read_true_updates_db_atomically(
        self, mongo_db, inbox_service,
    ):
        """`mark_as_read=True` → DB 의 read_at 이 모두 채워짐. atomic update_many."""
        repo = InboxRepository()
        await repo.insert(_make_inbox_item(target_id="FDP_1"))
        await repo.insert(_make_inbox_item(target_id="FDP_2", actor_id="USER_b"))

        await inbox_service.list_items(
            recipient_id="USER_recipient", mark_as_read=True,
        )

        coll = InboxItem.get_motor_collection()
        unread = await coll.count_documents(
            {"recipient_id": "USER_recipient", "read_at": None},
        )
        assert unread == 0


    async def test_response_is_read_reflects_pre_mark_state(
        self, mongo_db, inbox_service,
    ):
        """응답 dto 의 is_read 는 mark 전 상태 (False) — 인스타 강조 패턴.

        DB 는 mark 후 상태. 응답엔 read 전 상태. 다음 진입 시 강조 사라짐.
        """
        repo = InboxRepository()
        await repo.insert(_make_inbox_item())

        result = await inbox_service.list_items(
            recipient_id="USER_recipient", mark_as_read=True,
        )

        # 응답 — mark 전 상태
        assert result.items[0].is_read is False
        # DB — mark 후 상태
        coll = InboxItem.get_motor_collection()
        unread = await coll.count_documents(
            {"recipient_id": "USER_recipient", "read_at": None},
        )
        assert unread == 0


    async def test_mark_as_read_false_keeps_unread(
        self, mongo_db, inbox_service,
    ):
        """더 보기(`cursor` 있음) — mark_all_read 호출 안 됨. read_at 유지."""
        repo = InboxRepository()
        await repo.insert(_make_inbox_item())

        await inbox_service.list_items(
            recipient_id="USER_recipient", mark_as_read=False,
        )

        coll = InboxItem.get_motor_collection()
        unread = await coll.count_documents(
            {"recipient_id": "USER_recipient", "read_at": None},
        )
        assert unread == 1


# ──────────────────── hide — atomic + display=false 토글 ────────────────────

class TestHideAtomic:
    """`hide` 가 atomic update 로 권한 검증 + 토글."""

    async def test_hide_excludes_from_list(self, mongo_db, inbox_service):
        repo = InboxRepository()
        item = _make_inbox_item()
        await repo.insert(item)

        await inbox_service.hide_item(
            recipient_id="USER_recipient",
            inbox_item_id=str(item.id),
        )

        result = await inbox_service.list_items(
            recipient_id="USER_recipient",
        )
        assert result.items == []


    async def test_hide_other_user_raises_not_found(
        self, mongo_db, inbox_service,
    ):
        """타인 항목 hide 시도 → atomic query 매칭 실패 → NotFound 일원화."""
        repo = InboxRepository()
        item = _make_inbox_item(recipient_id="USER_other")
        await repo.insert(item)

        with pytest.raises(InboxItemNotFoundError):
            await inbox_service.hide_item(
                recipient_id="USER_recipient",
                inbox_item_id=str(item.id),
            )


    async def test_hide_invalid_objectid_raises_not_found(
        self, mongo_db, inbox_service,
    ):
        with pytest.raises(InboxItemNotFoundError):
            await inbox_service.hide_item(
                recipient_id="USER_recipient",
                inbox_item_id="not-an-objectid",
            )


# ──────────────────── count_unread + cap ────────────────────

class TestCountUnread:
    async def test_counts_only_unread_displayed(self, mongo_db, inbox_service):
        repo = InboxRepository()
        # 3건 insert — 모두 미읽음 / display=true
        for i in range(3):
            await repo.insert(_make_inbox_item(
                target_id=f"FDP_{i}", actor_id=f"USER_a_{i}",
            ))

        count = await inbox_service.count_unread(recipient_id="USER_recipient")

        assert count == 3


    async def test_excludes_hidden_items(
        self, mongo_db, inbox_service,
    ):
        """display=false (X 누름) 는 미읽음 카운트에서 제외."""
        repo = InboxRepository()
        n1 = _make_inbox_item(target_id="FDP_1")
        n2 = _make_inbox_item(target_id="FDP_2", actor_id="USER_b")
        await repo.insert(n1)
        await repo.insert(n2)

        await inbox_service.hide_item(
            recipient_id="USER_recipient", inbox_item_id=str(n1.id),
        )

        count = await inbox_service.count_unread(recipient_id="USER_recipient")

        assert count == 1


# ──────────────────── cascade_user_withdrawn ────────────────────

class TestCascadeUserWithdrawn:
    """탈퇴 cascade — recipient 또는 actor 매칭 항목 모두 삭제."""

    async def test_deletes_recipient_and_actor_matching(
        self, mongo_db, inbox_service,
    ):
        repo = InboxRepository()
        # USER_x 가 받은 항목
        await repo.insert(_make_inbox_item(
            recipient_id="USER_x", actor_id="USER_a",
        ))
        # USER_x 가 보낸 항목 (다른 사람이 받음)
        await repo.insert(_make_inbox_item(
            recipient_id="USER_b", actor_id="USER_x",
        ))
        # 무관한 항목 (보존되어야)
        await repo.insert(_make_inbox_item(
            recipient_id="USER_c", actor_id="USER_d",
        ))

        deleted = await inbox_service.cascade_user_withdrawn(user_id="USER_x")

        assert deleted == 2
        coll = InboxItem.get_motor_collection()
        assert await coll.count_documents({}) == 1
        # 무관한 항목은 보존
        remaining = await coll.find_one({})
        assert remaining["recipient_id"] == "USER_c"
