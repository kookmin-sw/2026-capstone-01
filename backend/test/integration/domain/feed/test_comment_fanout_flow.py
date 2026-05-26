"""피드 댓글 fan-out e2e 통합 테스트.

`create_comment` 호출 → RDB 댓글 INSERT → Mongo 인박스 적재 흐름의 통합 검증.

검증 매트릭스:

    | 시나리오                          | RDB 댓글  | Mongo 인박스 |
    |---|---|---|
    | 외부 actor 댓글                   | ✓         | ✓ 적재     |
    | 본인→본인 댓글                    | ✓         | ✗ skip     |
    | 같은 actor 가 여러 댓글 (다른 ID) | ✓ 여러 건 | ✓ 여러 건  |
    | delete_comment                    | RDB 삭제  | 항목 보존  |
    | 100자 초과 comment_preview        | -         | ellipsis   |
"""
import pytest

from app.domain.notification.model.inbox import InboxItem, InboxItemType


pytestmark = pytest.mark.integration


# ──────────────────── 정상 fan-out ────────────────────

class TestCreateCommentFanout:
    """`create_comment` 가 RDB INSERT 후 Mongo 에 댓글 인박스 적재."""

    async def test_external_actor_creates_inbox_item_with_comment_id(
        self, mongo_db, feed_post_comment_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post()
        actor_id = await _find_other_user(feed_post_comment_service.uow, owner_id)

        comment = await feed_post_comment_service.create_comment(
            user_id=actor_id, post_id=post_id, content="좋은 글이네요",
        )

        coll = InboxItem.get_motor_collection()
        doc = await coll.find_one({"recipient_id": owner_id})
        assert doc is not None
        assert doc["actor_id"] == actor_id
        assert doc["type"] == InboxItemType.FEED_COMMENT.value
        assert doc["comment_id"] == comment.comment_id
        assert doc["comment_preview"] == "좋은 글이네요"


    async def test_self_comment_does_not_create_inbox_item(
        self, mongo_db, feed_post_comment_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post()

        await feed_post_comment_service.create_comment(
            user_id=owner_id, post_id=post_id, content="self comment",
        )

        coll = InboxItem.get_motor_collection()
        assert await coll.count_documents({}) == 0


# ──────────────────── 멀티 댓글 (comment_id 자연 unique) ────────────────────

class TestMultipleCommentsCreateMultipleInboxItems:
    """같은 actor 가 여러 댓글 — comment_id 가 매번 달라 인박스 항목도 매번 새로 적재.

    좋아요와 차이점: 좋아요는 lifetime unique, 댓글은 comment_id 마다 별개.
    """

    async def test_three_comments_create_three_inbox_items(
        self, mongo_db, feed_post_comment_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post()
        actor_id = await _find_other_user(feed_post_comment_service.uow, owner_id)

        for i in range(3):
            await feed_post_comment_service.create_comment(
                user_id=actor_id, post_id=post_id, content=f"comment {i}",
            )

        coll = InboxItem.get_motor_collection()
        assert await coll.count_documents({"recipient_id": owner_id}) == 3


# ──────────────────── delete_comment — 인박스 보존 정책 ────────────────────

class TestDeleteCommentPreservesInboxItem:
    """댓글 삭제 시 인박스 cascade 안 함 — 좋아요 취소 인박스 보존 정책과 대칭."""

    async def test_delete_does_not_remove_inbox_item(
        self, mongo_db, feed_post_comment_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post()
        actor_id = await _find_other_user(feed_post_comment_service.uow, owner_id)

        comment = await feed_post_comment_service.create_comment(
            user_id=actor_id, post_id=post_id, content="hello",
        )
        await feed_post_comment_service.delete_comment(
            user_id=actor_id, post_id=post_id, comment_id=comment.comment_id,
        )

        # 인박스 항목 보존 — 이벤트 발생 사실의 기록
        coll = InboxItem.get_motor_collection()
        assert await coll.count_documents({"recipient_id": owner_id}) == 1


# ──────────────────── comment_preview ellipsis ────────────────────

class TestCommentPreviewTruncation:
    """100자 초과 댓글 → ellipsis 추가된 snapshot."""

    async def test_long_comment_truncated_with_ellipsis(
        self, mongo_db, feed_post_comment_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post()
        actor_id = await _find_other_user(feed_post_comment_service.uow, owner_id)

        long_text = "ㄱ" * 150
        await feed_post_comment_service.create_comment(
            user_id=actor_id, post_id=post_id, content=long_text,
        )

        coll = InboxItem.get_motor_collection()
        doc = await coll.find_one({"recipient_id": owner_id})
        assert len(doc["comment_preview"]) == 101  # 100 + "…"
        assert doc["comment_preview"].endswith("…")


# ──────────────────── helpers ────────────────────

async def _find_other_user(uow, exclude_user_id: str) -> str:
    from sqlalchemy import select
    from app.domain.auth.model.user import User, UserStatus

    async with uow as session:
        stmt = select(User.user_id).where(
            User.user_id != exclude_user_id, User.status == UserStatus.ACTIVE,
        ).limit(1)
        result = await session.execute(stmt)
        user_id = result.scalar_one_or_none()
        assert user_id is not None
        return user_id
