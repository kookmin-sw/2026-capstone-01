"""`access.load_viewable_post` 회귀 테스트.

해당 helper 가 좋아요 / 댓글 service 의 공통 진입점 — 깨지면 두 도메인의 가시성 검증이 동시에
무력화되므로 별도 단위로 cover.

검증:
    - 미존재 post                 → FeedNotFoundError (404)
    - 본인 글 fast-path           → block / friendship 조회 자체 안 함
    - 차단 관계                    → FeedBlockedError (403)
    - PUBLIC + 비친구             → 통과
    - FRIENDS + 친구              → 통과
    - FRIENDS + 비친구            → FeedNotFoundError (정보 누출 회피로 404)
    - PRIVATE + 비owner           → FeedNotFoundError (404)
"""
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
from test.unit.domain.feed.mock_factory import make_feed_post_with_counts
import pytest
from datetime import datetime, timezone

from app.domain.friend.model.friendship import FriendshipStatus
from app.domain.feed.service.exception import FeedBlockedError, FeedNotFoundError
from app.domain.feed.service.access import load_viewable_post
from app.domain.feed.model.feed_post import FeedPost, FeedVisibility


def _mk_row(post_id="FDP_x", user_id="USER_owner", visibility=FeedVisibility.PUBLIC):
    """`FeedPostWithCounts` 합성 — `find_by_post_id` 의 단일 SELECT row 형태.

    `load_viewable_post` 는 카운트 미사용이지만, repo 시그니처가 `Optional[FeedPostWithCounts]`
    라 wrapping 필요. counts 값은 의미 없으므로 default 0.
    """
    post = MagicMock(spec=FeedPost)
    post.post_id = post_id
    post.user_id = user_id
    post.visibility = visibility
    post.caption = None
    post.original_url = post.thumbnail_small_url = post.thumbnail_medium_url = "https://x"
    post.created_at = post.updated_at = datetime.now(timezone.utc)
    return make_feed_post_with_counts(post)


@pytest.fixture
def session():
    return MagicMock(name="session")


@pytest.fixture
def feed_repo_mock():
    return AsyncMock()


@pytest.fixture
def block_repo_mock():
    mock = AsyncMock()
    mock.find_blocks_between.return_value = []
    return mock


@pytest.fixture
def friendship_repo_mock():
    mock = AsyncMock()
    mock.find_between.return_value = None
    return mock


@pytest.fixture(autouse=True)
def _patch_repos(monkeypatch, feed_repo_mock, block_repo_mock, friendship_repo_mock):
    monkeypatch.setattr(
        "app.domain.feed.service.access.FeedPostRepository",
        lambda s: feed_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.feed.service.access.UserBlockRepository",
        lambda s: block_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.feed.service.access.FriendshipRepository",
        lambda s: friendship_repo_mock,
    )


# ──────────────────── 미존재 ────────────────────

@pytest.mark.unit
class TestMissingPost:
    async def test_raises_not_found(self, session, feed_repo_mock):
        feed_repo_mock.find_by_post_id.return_value = None
        with pytest.raises(FeedNotFoundError):
            await load_viewable_post(session, viewer_id="USER_a", post_id="FDP_missing")


# ──────────────────── 본인 fast-path ────────────────────

@pytest.mark.unit
class TestOwnerFastPath:
    @pytest.mark.parametrize("visibility", list(FeedVisibility))
    async def test_owner_can_view_any_visibility_without_db_hit(
        self, session, feed_repo_mock, block_repo_mock, friendship_repo_mock,
        visibility,
    ):
        feed_repo_mock.find_by_post_id.return_value = _mk_row(
            user_id="USER_a", visibility=visibility,
        )
        result = await load_viewable_post(session, viewer_id="USER_a", post_id="FDP_x")
        assert result.user_id == "USER_a"
        # 본인은 차단/친구 조회 자체를 안 함
        block_repo_mock.find_blocks_between.assert_not_called()
        friendship_repo_mock.find_between.assert_not_called()


# ──────────────────── 차단 ────────────────────

@pytest.mark.unit
class TestBlocked:
    async def test_either_direction_block_raises(
        self, session, feed_repo_mock, block_repo_mock, friendship_repo_mock,
    ):
        feed_repo_mock.find_by_post_id.return_value = _mk_row(user_id="USER_owner")
        block_repo_mock.find_blocks_between.return_value = [object()]

        with pytest.raises(FeedBlockedError):
            await load_viewable_post(session, viewer_id="USER_v", post_id="FDP_x")
        # 차단 후 friend 조회 안 함 (불필요)
        friendship_repo_mock.find_between.assert_not_called()


# ──────────────────── visibility 분기 (비owner) ────────────────────

@pytest.mark.unit
class TestVisibilityDecision:
    async def test_public_visible_to_non_friend(
        self, session, feed_repo_mock,
    ):
        feed_repo_mock.find_by_post_id.return_value = _mk_row(visibility=FeedVisibility.PUBLIC)
        result = await load_viewable_post(session, viewer_id="USER_v", post_id="FDP_x")
        assert result.visibility == FeedVisibility.PUBLIC


    async def test_friends_only_visible_to_friend(
        self, session, feed_repo_mock, friendship_repo_mock,
    ):
        feed_repo_mock.find_by_post_id.return_value = _mk_row(visibility=FeedVisibility.FRIENDS)
        friendship_repo_mock.find_between.return_value = SimpleNamespace(
            status=FriendshipStatus.ACCEPTED,
        )
        result = await load_viewable_post(session, viewer_id="USER_v", post_id="FDP_x")
        assert result.visibility == FeedVisibility.FRIENDS


    async def test_friends_only_invisible_to_non_friend_returns_not_found(
        self, session, feed_repo_mock, friendship_repo_mock,
    ):
        """정보 누출 회피 — 403 이 아닌 404 로 응답."""
        feed_repo_mock.find_by_post_id.return_value = _mk_row(visibility=FeedVisibility.FRIENDS)
        friendship_repo_mock.find_between.return_value = None
        with pytest.raises(FeedNotFoundError):
            await load_viewable_post(session, viewer_id="USER_v", post_id="FDP_x")


    async def test_pending_friendship_treated_as_non_friend(
        self, session, feed_repo_mock, friendship_repo_mock,
    ):
        """ACCEPTED 외 (PENDING/REJECTED) 는 비친구 — FRIENDS 글 못 봄."""
        feed_repo_mock.find_by_post_id.return_value = _mk_row(visibility=FeedVisibility.FRIENDS)
        friendship_repo_mock.find_between.return_value = SimpleNamespace(
            status=FriendshipStatus.PENDING,
        )
        with pytest.raises(FeedNotFoundError):
            await load_viewable_post(session, viewer_id="USER_v", post_id="FDP_x")


    async def test_private_invisible_to_non_owner(
        self, session, feed_repo_mock, friendship_repo_mock,
    ):
        feed_repo_mock.find_by_post_id.return_value = _mk_row(visibility=FeedVisibility.PRIVATE)
        friendship_repo_mock.find_between.return_value = SimpleNamespace(
            status=FriendshipStatus.ACCEPTED,
        )
        # 친구라도 PRIVATE 은 본인 외 못 봄
        with pytest.raises(FeedNotFoundError):
            await load_viewable_post(session, viewer_id="USER_v", post_id="FDP_x")
