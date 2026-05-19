"""`get_user_feed` + `_resolve_viewer_visibilities` 통합 회귀 테스트.

`can_view` 의 8 케이스 매트릭스는 visibility/test_can_view.py 가 cover. 본 파일은:
    - `_resolve_viewer_visibilities` 가 viewer 관계 (본인/친구/비친구/차단) 별로
      올바른 visibility IN-list 를 만들어 repo 에 전달하는지
    - 차단 관계에서 `FeedBlockedError` raise + repo 호출 자체 안 일어남
    - 본인 fast-path 에서 friend / block 조회 자체를 건너뜀 (DB hit 절약)
    - 페이지네이션 next_cursor 가 페이지 가득 찰 때만 채워짐 (get_my_feed 와 동일 약속)
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.domain.feed.model.feed_post import FeedPost, FeedVisibility
from app.domain.feed.service.exception import FeedBlockedError
from app.domain.friend.model.friendship import FriendshipStatus

from test.unit.domain.feed.mock_factory import make_feed_post_with_counts


def _mk_row(
    post_id="FDP_x",
    user_id="USER_owner",
    visibility=FeedVisibility.PUBLIC,
    *,
    like_count=0,
    comment_count=0,
):
    """`FeedPostWithCounts` 합성 — repo (`find_by_owner`) 의 단일 SELECT row 형태."""
    post = MagicMock(spec=FeedPost)
    post.post_id = post_id
    post.user_id = user_id
    post.visibility = visibility
    post.caption = None
    post.original_url = "https://x/o.jpg"
    post.thumbnail_small_url = "https://x/s.jpg"
    post.thumbnail_medium_url = "https://x/m.jpg"
    post.created_at = datetime.now(timezone.utc)
    post.updated_at = datetime.now(timezone.utc)
    return make_feed_post_with_counts(
        post, like_count=like_count, comment_count=comment_count,
    )


def _accepted_friendship() -> SimpleNamespace:
    return SimpleNamespace(status=FriendshipStatus.ACCEPTED)


def _pending_friendship() -> SimpleNamespace:
    """관계는 있지만 ACCEPTED 가 아닌 케이스 — `is_friend=False` 로 취급되어야 함."""
    return SimpleNamespace(status=FriendshipStatus.PENDING)


# ──────────────────── visibilities 부분집합 결정 ────────────────────

@pytest.mark.unit
class TestVisibilityResolution:
    async def test_self_passes_all_visibilities_without_db_hit(
        self, service, repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        """본인 fast-path — friend/block 조회 자체를 안 함."""
        repo_mock.find_by_owner.return_value = []

        await service.get_user_feed(viewer_id="USER_a", owner_id="USER_a")

        assert set(repo_mock.find_by_owner.await_args.kwargs["visibilities"]) == set(FeedVisibility)
        friendship_repo_mock.find_between.assert_not_called()
        block_repo_mock.find_blocks_between.assert_not_called()

    async def test_friend_sees_friends_and_public(
        self, service, repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        block_repo_mock.find_blocks_between.return_value = []
        friendship_repo_mock.find_between.return_value = _accepted_friendship()
        repo_mock.find_by_owner.return_value = []

        await service.get_user_feed(viewer_id="USER_a", owner_id="USER_b")

        passed = set(repo_mock.find_by_owner.await_args.kwargs["visibilities"])
        assert passed == {FeedVisibility.FRIENDS, FeedVisibility.PUBLIC}

    async def test_pending_friendship_treated_as_non_friend(
        self, service, repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        """ACCEPTED 외 (PENDING/REJECTED) 는 `is_friend=False` — FRIENDS 미노출."""
        block_repo_mock.find_blocks_between.return_value = []
        friendship_repo_mock.find_between.return_value = _pending_friendship()
        repo_mock.find_by_owner.return_value = []

        await service.get_user_feed(viewer_id="USER_a", owner_id="USER_b")

        passed = set(repo_mock.find_by_owner.await_args.kwargs["visibilities"])
        assert passed == {FeedVisibility.PUBLIC}

    async def test_non_friend_sees_only_public(
        self, service, repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        block_repo_mock.find_blocks_between.return_value = []
        friendship_repo_mock.find_between.return_value = None
        repo_mock.find_by_owner.return_value = []

        await service.get_user_feed(viewer_id="USER_a", owner_id="USER_b")

        passed = set(repo_mock.find_by_owner.await_args.kwargs["visibilities"])
        assert passed == {FeedVisibility.PUBLIC}


# ──────────────────── 차단 거부 ────────────────────

@pytest.mark.unit
class TestBlockedRaisesAndDoesNotQueryFeed:
    async def test_either_direction_block_raises(
        self, service, repo_mock, block_repo_mock, friendship_repo_mock,
    ):
        """차단 어느 방향이든 (`viewer→owner` or `owner→viewer`) 한 row 만 있어도 거절."""
        block_repo_mock.find_blocks_between.return_value = [object()]  # 방향 무관 1+ row

        with pytest.raises(FeedBlockedError):
            await service.get_user_feed(viewer_id="USER_a", owner_id="USER_b")

        # 차단이면 friend 조회도, feed 조회도 모두 일어나면 안 됨
        friendship_repo_mock.find_between.assert_not_called()
        repo_mock.find_by_owner.assert_not_called()


# ──────────────────── 페이지네이션 ────────────────────

@pytest.mark.unit
class TestPagination:
    async def test_next_cursor_when_full_page(
        self, service, repo_mock, friendship_repo_mock, block_repo_mock, monkeypatch,
    ):
        monkeypatch.setattr("app.domain.feed.service.feed_post.PAGE_SIZE", 2)
        block_repo_mock.find_blocks_between.return_value = []
        friendship_repo_mock.find_between.return_value = None
        repo_mock.find_by_owner.return_value = [
            _mk_row(post_id="FDP_0"),
            _mk_row(post_id="FDP_1"),
        ]

        result = await service.get_user_feed(viewer_id="USER_a", owner_id="USER_b")
        assert result.next_cursor == "FDP_1"

    async def test_next_cursor_none_when_partial_page(
        self, service, repo_mock, friendship_repo_mock, block_repo_mock, monkeypatch,
    ):
        monkeypatch.setattr("app.domain.feed.service.feed_post.PAGE_SIZE", 5)
        block_repo_mock.find_blocks_between.return_value = []
        friendship_repo_mock.find_between.return_value = None
        repo_mock.find_by_owner.return_value = [_mk_row(post_id=f"FDP_{i}") for i in range(3)]

        result = await service.get_user_feed(viewer_id="USER_a", owner_id="USER_b")
        assert result.next_cursor is None

    async def test_cursor_passes_through_to_repo(
        self, service, repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        block_repo_mock.find_blocks_between.return_value = []
        friendship_repo_mock.find_between.return_value = None
        repo_mock.find_by_owner.return_value = []

        await service.get_user_feed(viewer_id="USER_a", owner_id="USER_b", cursor="FDP_seed")
        assert repo_mock.find_by_owner.await_args.kwargs["cursor"] == "FDP_seed"


# ──────────────────── viewer_id 전파 + is_liked 매핑 ────────────────────

@pytest.mark.unit
class TestViewerIdPropagation:
    """get_user_feed 호출이 repo 에 viewer_id 를 정확히 전달하는지 — 이 값이 빠지면
    `find_by_owner` 의 is_liked subquery 가 단락되어 응답이 항상 False 가 되는 silent 회귀가
    발생함. 따라서 service↔repo 경계에서 명시적으로 검증한다.
    """
    async def test_viewer_id_is_forwarded_to_repo(
        self, service, repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        block_repo_mock.find_blocks_between.return_value = []
        friendship_repo_mock.find_between.return_value = None
        repo_mock.find_by_owner.return_value = []

        await service.get_user_feed(viewer_id="USER_v", owner_id="USER_b")

        assert repo_mock.find_by_owner.await_args.kwargs["viewer_id"] == "USER_v"

    async def test_self_view_passes_self_as_viewer_id(
        self, service, repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        """viewer==owner 본인 케이스도 viewer_id 가 owner 와 동일하게 전달돼야
        본인이 본인 글에 누른 좋아요(인스타 동치)가 응답에 반영된다.
        """
        repo_mock.find_by_owner.return_value = []

        await service.get_user_feed(viewer_id="USER_a", owner_id="USER_a")

        assert repo_mock.find_by_owner.await_args.kwargs["viewer_id"] == "USER_a"


@pytest.mark.unit
class TestIsLikedMappedFromRow:
    """repo 가 반환한 row.is_liked 가 응답 DTO 까지 정확히 흘러가는지 — _to_dto 누락 회귀 가드.
    """
    async def test_row_is_liked_true_propagates_to_dto(
        self, service, repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        block_repo_mock.find_blocks_between.return_value = []
        friendship_repo_mock.find_between.return_value = None
        row = make_feed_post_with_counts(
            _mk_row(post_id="FDP_liked").post, is_liked=True,
        )
        repo_mock.find_by_owner.return_value = [row]

        result = await service.get_user_feed(viewer_id="USER_v", owner_id="USER_b")

        assert result.posts[0].is_liked is True

    async def test_row_is_liked_false_propagates_to_dto(
        self, service, repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        block_repo_mock.find_blocks_between.return_value = []
        friendship_repo_mock.find_between.return_value = None
        row = make_feed_post_with_counts(
            _mk_row(post_id="FDP_unliked").post, is_liked=False,
        )
        repo_mock.find_by_owner.return_value = [row]

        result = await service.get_user_feed(viewer_id="USER_v", owner_id="USER_b")

        assert result.posts[0].is_liked is False
