"""트립메이트 좋아요 fan-out e2e 통합 테스트.

`add_like` 호출 → RDB 좋아요 INSERT → Mongo 인박스 적재 흐름 통합 검증. feed 도메인과 달리
visibility/차단 검증이 없어 흐름이 더 단순. `target_preview` 가 `post.title` 인 점이
검증 포인트.

검증 매트릭스:

    | 시나리오                          | RDB 좋아요 | Mongo 인박스 |
    |---|---|---|
    | 외부 actor 좋아요                 | ✓          | ✓ (target_preview = title) |
    | 본인→본인 좋아요                  | ✓          | ✗ skip     |
    | 좋아요-취소-좋아요 멱등           | RDB 1번만  | 1건 유지   |
    | remove_like                       | RDB 삭제   | 항목 보존  |
"""
import pytest

from app.domain.notification.model.inbox import (
    InboxItem,
    InboxItemType,
    TargetType,
)


pytestmark = pytest.mark.integration


# ──────────────────── 정상 fan-out ────────────────────

class TestAddLikeFanout:
    """`add_like` 가 RDB INSERT 후 Mongo 에 인박스 적재 — `target_preview` = post.title."""

    async def test_external_actor_creates_inbox_item_with_title_preview(
        self, mongo_db, tripmate_post_like_service, seed_tripmate_post,
    ):
        post_id, owner_id = await seed_tripmate_post()
        actor_id = await _find_other_user(tripmate_post_like_service.uow, owner_id)

        await tripmate_post_like_service.add_like(user_id=actor_id, post_id=post_id)

        coll = InboxItem.get_motor_collection()
        doc = await coll.find_one({"recipient_id": owner_id})
        assert doc is not None
        assert doc["actor_id"] == actor_id
        assert doc["type"] == InboxItemType.TRIPMATE_LIKE.value
        assert doc["target_type"] == TargetType.TRIPMATE_POST.value
        assert doc["target_id"] == post_id
        # tripmate 의 target_preview 는 post.title
        assert doc["target_preview"] == "여행 같이 가실 분"


    async def test_self_like_does_not_create_inbox_item(
        self, mongo_db, tripmate_post_like_service, seed_tripmate_post,
    ):
        post_id, owner_id = await seed_tripmate_post()

        like_count = await tripmate_post_like_service.add_like(
            user_id=owner_id, post_id=post_id,
        )

        assert like_count == 1
        coll = InboxItem.get_motor_collection()
        assert await coll.count_documents({}) == 0


# ──────────────────── 멱등성 ────────────────────

class TestLikeIdempotency:
    async def test_like_cancel_like_keeps_single_inbox_item(
        self, mongo_db, tripmate_post_like_service, seed_tripmate_post,
    ):
        post_id, owner_id = await seed_tripmate_post()
        actor_id = await _find_other_user(tripmate_post_like_service.uow, owner_id)

        await tripmate_post_like_service.add_like(user_id=actor_id, post_id=post_id)
        await tripmate_post_like_service.remove_like(user_id=actor_id, post_id=post_id)
        await tripmate_post_like_service.add_like(user_id=actor_id, post_id=post_id)

        coll = InboxItem.get_motor_collection()
        assert await coll.count_documents({"recipient_id": owner_id}) == 1


# ──────────────────── remove_like — 인박스 보존 ────────────────────

class TestRemoveLikePreservesInboxItem:
    async def test_remove_does_not_delete_inbox_item(
        self, mongo_db, tripmate_post_like_service, seed_tripmate_post,
    ):
        post_id, owner_id = await seed_tripmate_post()
        actor_id = await _find_other_user(tripmate_post_like_service.uow, owner_id)

        await tripmate_post_like_service.add_like(user_id=actor_id, post_id=post_id)
        await tripmate_post_like_service.remove_like(user_id=actor_id, post_id=post_id)

        coll = InboxItem.get_motor_collection()
        assert await coll.count_documents({"recipient_id": owner_id}) == 1


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
