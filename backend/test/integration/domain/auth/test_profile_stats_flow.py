"""ProfileService.get_my_stats e2e 통합 — 실 PostgreSQL 회귀 가드.

검증 매트릭스:

    | 시나리오                                | 기대                       |
    |---|---|
    | 활동 없음 (피드 0, 친구 0)              | total_feed_likes=0, total_friends=0 |
    | 본인 피드에 외부 좋아요 N건             | total_feed_likes=N         |
    | 다른 유저의 피드 좋아요는 비합산         | 본인 피드만 카운트 (privacy / 정확도) |
    | PRIVATE 게시물에 받은 좋아요도 포함     | visibility 무관 합산        |
    | ACCEPTED 친구 + PENDING 요청 혼재       | ACCEPTED 만 카운트          |
    | requester / addressee 양쪽 친구         | 둘 다 합산 (방향 무관)      |
    | 존재하지 않는 user_id                   | ValueError                 |

좋아요 카운트는 cross-domain JOIN (feed_post_like ⨝ feed_post) SQL 동작 검증이
unit 으론 잡히지 않는다. friendship OR-조건의 BitmapOr 인덱스 사용도 마찬가지로 실 PG.
"""
import pytest

from app.domain.feed.model.feed_post import FeedPost, FeedVisibility
from app.domain.feed.model.feed_post_like import FeedPostLike
from app.domain.friend.model.friendship import Friendship, FriendshipStatus


pytestmark = pytest.mark.integration


# ──────────────────── helpers ────────────────────

async def _insert_post(
    session_factory,
    owner_id: str,
    visibility: FeedVisibility = FeedVisibility.PUBLIC,
) -> str:
    async with session_factory() as session:
        post = FeedPost(
            user_id=owner_id,
            visibility=visibility,
            caption=None,
            original_url="https://x/o.jpg",
            thumbnail_small_url="https://x/s.jpg",
            thumbnail_medium_url="https://x/m.jpg",
        )
        session.add(post)
        await session.commit()
        return post.post_id


async def _insert_like(session_factory, user_id: str, post_id: str) -> None:
    async with session_factory() as session:
        session.add(FeedPostLike(user_id=user_id, post_id=post_id))
        await session.commit()


async def _insert_friendship(
    session_factory,
    requester_id: str,
    addressee_id: str,
    status: FriendshipStatus,
) -> None:
    async with session_factory() as session:
        session.add(Friendship(
            requester_id=requester_id,
            addressee_id=addressee_id,
            status=status,
        ))
        await session.commit()


# ──────────────────── happy path / 빈 케이스 ────────────────────

class TestEmptyActivity:
    async def test_no_posts_no_friends_returns_zero(
        self, profile_service, seed_users,
    ):
        [me_id] = await seed_users(1)

        result = await profile_service.get_my_stats(me_id)

        assert result.total_feed_likes == 0
        assert result.total_friends == 0


# ──────────────────── total_feed_likes 정합성 ────────────────────

class TestFeedLikeAggregation:
    async def test_counts_likes_on_my_posts(
        self, profile_service, seed_users, session_factory,
    ):
        """내 피드에 받은 좋아요만 정확히 합산."""
        me_id, liker1, liker2, liker3 = await seed_users(4)
        post_a = await _insert_post(session_factory, me_id)
        post_b = await _insert_post(session_factory, me_id)
        # post_a 에 2건, post_b 에 1건 — 총 3건
        await _insert_like(session_factory, liker1, post_a)
        await _insert_like(session_factory, liker2, post_a)
        await _insert_like(session_factory, liker3, post_b)

        result = await profile_service.get_my_stats(me_id)
        assert result.total_feed_likes == 3

    async def test_does_not_count_likes_on_other_users_posts(
        self, profile_service, seed_users, session_factory,
    ):
        """다른 유저의 피드가 받은 좋아요는 내 stats 에 포함되지 않음 (privacy / 정확도)."""
        me_id, other_id, liker = await seed_users(3)
        other_post = await _insert_post(session_factory, other_id)
        await _insert_like(session_factory, liker, other_post)
        # 나는 내 글에 받은 좋아요가 없음 + 다른 사람 글의 좋아요는 누락돼야 함
        await _insert_like(session_factory, me_id, other_post)

        result = await profile_service.get_my_stats(me_id)
        assert result.total_feed_likes == 0

    async def test_private_visibility_likes_also_counted(
        self, profile_service, seed_users, session_factory,
    ):
        """PRIVATE 게시물이 받은 좋아요도 본인 stats 에는 합산 (visibility 무관)."""
        me_id, liker = await seed_users(2)
        private_post = await _insert_post(
            session_factory, me_id, visibility=FeedVisibility.PRIVATE,
        )
        await _insert_like(session_factory, liker, private_post)

        result = await profile_service.get_my_stats(me_id)
        assert result.total_feed_likes == 1

    async def test_self_like_on_own_post_counted(
        self, profile_service, seed_users, session_factory,
    ):
        """본인이 본인 글에 누른 좋아요도 합산 (인스타 동치 — 본인 좋아요 허용)."""
        [me_id] = await seed_users(1)
        post = await _insert_post(session_factory, me_id)
        await _insert_like(session_factory, me_id, post)

        result = await profile_service.get_my_stats(me_id)
        assert result.total_feed_likes == 1


# ──────────────────── total_friends 정합성 ────────────────────

class TestFriendshipCount:
    async def test_counts_only_accepted_status(
        self, profile_service, seed_users, session_factory,
    ):
        """PENDING / REJECTED 친구는 제외. ACCEPTED 만 카운트."""
        me_id, accepted_peer, pending_peer = await seed_users(3)
        await _insert_friendship(
            session_factory, me_id, accepted_peer, FriendshipStatus.ACCEPTED,
        )
        await _insert_friendship(
            session_factory, me_id, pending_peer, FriendshipStatus.PENDING,
        )

        result = await profile_service.get_my_stats(me_id)
        assert result.total_friends == 1

    async def test_counts_friendship_in_both_directions(
        self, profile_service, seed_users, session_factory,
    ):
        """내가 requester 인 친구와 addressee 인 친구 모두 합산 (방향 무관)."""
        me_id, friend_a, friend_b = await seed_users(3)
        # 내가 requester
        await _insert_friendship(
            session_factory, me_id, friend_a, FriendshipStatus.ACCEPTED,
        )
        # 내가 addressee
        await _insert_friendship(
            session_factory, friend_b, me_id, FriendshipStatus.ACCEPTED,
        )

        result = await profile_service.get_my_stats(me_id)
        assert result.total_friends == 2

    async def test_does_not_count_unrelated_friendships(
        self, profile_service, seed_users, session_factory,
    ):
        """다른 두 유저 사이의 친구 관계는 내 카운트와 무관."""
        me_id, u1, u2 = await seed_users(3)
        # 나와 무관한 친구 관계
        await _insert_friendship(
            session_factory, u1, u2, FriendshipStatus.ACCEPTED,
        )

        result = await profile_service.get_my_stats(me_id)
        assert result.total_friends == 0


# ──────────────────── 권한 / 에러 ────────────────────

class TestErrors:
    async def test_unknown_user_id_raises_value_error(self, profile_service):
        """존재하지 않는 user_id → ValueError (라우터에서 404 매핑)."""
        with pytest.raises(ValueError):
            await profile_service.get_my_stats("USER_does_not_exist")


# ──────────────────── 통합 — 좋아요/친구 같이 ────────────────────

class TestCombined:
    async def test_likes_and_friends_aggregated_independently(
        self, profile_service, seed_users, session_factory,
    ):
        """두 카운트가 서로 영향 주지 않고 독립적으로 정확히 합산 — DTO 매핑 회귀 가드."""
        me_id, liker, friend = await seed_users(3)
        post = await _insert_post(session_factory, me_id)
        await _insert_like(session_factory, liker, post)
        await _insert_friendship(
            session_factory, me_id, friend, FriendshipStatus.ACCEPTED,
        )

        result = await profile_service.get_my_stats(me_id)
        assert result.total_feed_likes == 1
        assert result.total_friends == 1
