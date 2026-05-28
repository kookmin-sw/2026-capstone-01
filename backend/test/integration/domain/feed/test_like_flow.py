"""FeedPostLikeService — visibility / 차단 cross-domain e2e 통합 테스트.

`load_viewable_post` (access.py 의 free function) 의 합성 로직이 실 RDB 의 friendship +
user_block 테이블과 정확히 결합하는지 검증. fan-out 측면은 Phase A 가 cover —
본 모듈은 가시성 가드 자체에 집중.

검증 매트릭스:

    | post visibility | viewer 관계      | 기대 결과              |
    |---|---|---|
    | PUBLIC          | 비친구           | ✅ 좋아요 가능          |
    | PUBLIC          | 차단              | ❌ FeedBlockedError    |
    | FRIENDS         | ACCEPTED 친구    | ✅ 좋아요 가능          |
    | FRIENDS         | 비친구           | ❌ FeedNotFoundError   |
    | PRIVATE         | 본인              | ✅ 좋아요 가능          |
    | PRIVATE         | 타인              | ❌ FeedNotFoundError   |

차단 → 403, visibility 미충족 → 404. 정보 누출 회피 정책 일관.
"""
import pytest

from app.domain.feed.service.exception import FeedBlockedError, FeedNotFoundError
from app.domain.feed.model.feed_post import FeedVisibility


pytestmark = pytest.mark.integration


# ──────────────────── PUBLIC ────────────────────

class TestPublicVisibility:
    """PUBLIC 게시물 — 차단 외 누구나 좋아요."""

    async def test_stranger_can_like(
        self, mongo_db, feed_post_like_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post(visibility=FeedVisibility.PUBLIC)
        actor_id = await _find_other_user(feed_post_like_service.uow, owner_id)

        like_count = await feed_post_like_service.add_like(
            user_id=actor_id, post_id=post_id,
        )

        assert like_count == 1


    async def test_blocked_user_raises_blocked_error(
        self, mongo_db, feed_post_like_service, seed_feed_post, seed_block,
    ):
        """owner ↔ actor 차단 관계 → FeedBlockedError. 좋아요 자체 차단."""
        post_id, owner_id = await seed_feed_post(visibility=FeedVisibility.PUBLIC)
        actor_id = await _find_other_user(feed_post_like_service.uow, owner_id)

        await seed_block(blocker=owner_id, blocked=actor_id)

        with pytest.raises(FeedBlockedError):
            await feed_post_like_service.add_like(user_id=actor_id, post_id=post_id)


# ──────────────────── FRIENDS ────────────────────

class TestFriendsVisibility:
    """FRIENDS 게시물 — ACCEPTED 친구만 좋아요. 비친구 → 404 (정보 누출 회피)."""

    async def test_friend_can_like(
        self, mongo_db, feed_post_like_service, seed_feed_post, seed_friendship,
    ):
        post_id, owner_id = await seed_feed_post(visibility=FeedVisibility.FRIENDS)
        actor_id = await _find_other_user(feed_post_like_service.uow, owner_id)

        await seed_friendship(owner_id, actor_id)

        like_count = await feed_post_like_service.add_like(
            user_id=actor_id, post_id=post_id,
        )

        assert like_count == 1


    async def test_non_friend_raises_not_found(
        self, mongo_db, feed_post_like_service, seed_feed_post,
    ):
        """비친구 → FeedNotFoundError (404). 403 대신 404 → 게시물 존재 자체 누출 회피."""
        post_id, owner_id = await seed_feed_post(visibility=FeedVisibility.FRIENDS)
        actor_id = await _find_other_user(feed_post_like_service.uow, owner_id)

        with pytest.raises(FeedNotFoundError):
            await feed_post_like_service.add_like(user_id=actor_id, post_id=post_id)


# ──────────────────── PRIVATE ────────────────────

class TestPrivateVisibility:
    """PRIVATE 게시물 — 본인만 좋아요. 타인 → 404."""

    async def test_owner_can_like_own_private(
        self, mongo_db, feed_post_like_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post(visibility=FeedVisibility.PRIVATE)

        like_count = await feed_post_like_service.add_like(
            user_id=owner_id, post_id=post_id,
        )

        assert like_count == 1


    async def test_stranger_raises_not_found(
        self, mongo_db, feed_post_like_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post(visibility=FeedVisibility.PRIVATE)
        actor_id = await _find_other_user(feed_post_like_service.uow, owner_id)

        with pytest.raises(FeedNotFoundError):
            await feed_post_like_service.add_like(user_id=actor_id, post_id=post_id)


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
