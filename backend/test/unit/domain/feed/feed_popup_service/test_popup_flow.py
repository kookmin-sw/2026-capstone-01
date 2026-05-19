"""FeedPopupService.get_popup 회귀 테스트.

검증:
    - user 미존재 → PopupTargetNotFoundError (404 매핑)
    - 회원가입 미완료 (detail 결손) → 동일 PopupTargetNotFoundError (enumeration 회피)
    - 차단 → access 의 FeedBlockedError 그대로 propagate (catch 안 함)
    - 정상: 프로필 5종 + 최근 9개 feed 매핑
    - feed_repo 호출이 limit=9 + cursor=None 으로 일어남 (popup spec)
    - 비친구 → visibilities=[PUBLIC] 만 받아 그대로 repo 에 전달
    - viewer == owner / 친구 시나리오 — access stub 으로 visibilities 변경 후 검증
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.domain.auth.model.user_travel_style import TravelStyle
from app.domain.feed.dto.feed_popup import POPUP_FEED_LIMIT
from app.domain.feed.dto.feed_post import FeedPostWithCounts
from app.domain.feed.model.feed_post import FeedPost, FeedVisibility
from app.domain.feed.service.exception import (
    FeedBlockedError,
    PopupTargetNotFoundError,
)

from test.unit.domain.feed.mock_factory import make_user_with_profile_mock


def _mk_feed_row(post_id="FDP_x", user_id="USER_owner", like_count=0, comment_count=0):
    """`FeedPostWithCounts` 합성 — popup 의 feed item 시뮬레이션."""
    post = MagicMock(spec=FeedPost)
    post.post_id = post_id
    post.user_id = user_id
    post.visibility = FeedVisibility.PUBLIC
    post.caption = None
    post.original_url = post.thumbnail_small_url = post.thumbnail_medium_url = "https://x"
    post.created_at = post.updated_at = datetime.now(timezone.utc)
    return FeedPostWithCounts(
        post=post,
        like_count=like_count,
        comment_count=comment_count,
        is_liked=False,
    )


# ──────────────────── user 미존재 / 결손 ────────────────────

@pytest.mark.unit
class TestUserMissing:
    async def test_user_not_found_raises(self, service, user_repo_mock, feed_repo_mock):
        user_repo_mock.find_by_id_with_profile.return_value = None
        with pytest.raises(PopupTargetNotFoundError):
            await service.get_popup(viewer_id="USER_v", owner_id="USER_ghost")
        # 미존재면 feed 조회도 안 일어남 — 단순 404, 추가 비용 없음.
        feed_repo_mock.find_by_owner.assert_not_called()

    async def test_detail_missing_raises_same_error(
        self, service, user_repo_mock, feed_repo_mock,
    ):
        """회원가입 미완료 (detail=None) 와 user 미존재 → 같은 404 (enumeration 회피)."""
        user_repo_mock.find_by_id_with_profile.return_value = make_user_with_profile_mock(
            detail_present=False,
        )
        with pytest.raises(PopupTargetNotFoundError):
            await service.get_popup(viewer_id="USER_v", owner_id="USER_x")
        feed_repo_mock.find_by_owner.assert_not_called()


# ──────────────────── 차단 propagate ────────────────────

@pytest.mark.unit
class TestBlockedPropagation:
    async def test_blocked_raises_without_feed_query(
        self, service, user_repo_mock, feed_repo_mock, monkeypatch,
    ):
        """차단 → access 가 FeedBlockedError raise → service 가 catch 안 함."""
        user_repo_mock.find_by_id_with_profile.return_value = make_user_with_profile_mock()

        async def _raise(session, *, viewer_id, owner_id):
            raise FeedBlockedError("차단 관계")
        monkeypatch.setattr(
            "app.domain.feed.service.feed_popup.resolve_viewer_visibilities", _raise,
        )

        with pytest.raises(FeedBlockedError):
            await service.get_popup(viewer_id="USER_v", owner_id="USER_owner")
        # 차단 시 feed 조회 안 일어남 — user 정보 노출도 차단됨.
        feed_repo_mock.find_by_owner.assert_not_called()


# ──────────────────── 정상 합성 ────────────────────

@pytest.mark.unit
class TestPopupAssembly:
    async def test_maps_profile_fields(self, service, user_repo_mock, feed_repo_mock):
        user_repo_mock.find_by_id_with_profile.return_value = make_user_with_profile_mock(
            user_id="USER_owner", user_name="조현상", nationality="korea",
            travel_styles=[TravelStyle.ACTIVITY, TravelStyle.FOOD_TOUR],
            profile_image_url="https://x/p.jpg",
        )
        feed_repo_mock.find_by_owner.return_value = []

        result = await service.get_popup(viewer_id="USER_v", owner_id="USER_owner")

        assert result.user_id == "USER_owner"
        assert result.user_name == "조현상"
        assert result.nationality == "korea"
        assert result.travel_styles == [TravelStyle.ACTIVITY, TravelStyle.FOOD_TOUR]
        assert result.profile_image_url == "https://x/p.jpg"
        assert result.feed_items == []

    async def test_feed_items_mapped_with_counts(
        self, service, user_repo_mock, feed_repo_mock,
    ):
        user_repo_mock.find_by_id_with_profile.return_value = make_user_with_profile_mock()
        feed_repo_mock.find_by_owner.return_value = [
            _mk_feed_row(post_id="FDP_a", like_count=5, comment_count=1),
            _mk_feed_row(post_id="FDP_b", like_count=0, comment_count=3),
        ]
        result = await service.get_popup(viewer_id="USER_v", owner_id="USER_owner")

        assert len(result.feed_items) == 2
        assert result.feed_items[0].post_id == "FDP_a"
        assert result.feed_items[0].like_count == 5
        assert result.feed_items[0].comment_count == 1
        assert result.feed_items[1].post_id == "FDP_b"
        assert result.feed_items[1].like_count == 0
        assert result.feed_items[1].comment_count == 3


# ──────────────────── feed repo 호출 contract ────────────────────

@pytest.mark.unit
class TestFeedRepoContract:
    async def test_calls_find_by_owner_with_limit_9_no_cursor(
        self, service, user_repo_mock, feed_repo_mock,
    ):
        """popup 은 첫 페이지 9개 fixed — limit=POPUP_FEED_LIMIT, cursor 미제공."""
        user_repo_mock.find_by_id_with_profile.return_value = make_user_with_profile_mock()
        feed_repo_mock.find_by_owner.return_value = []

        await service.get_popup(viewer_id="USER_v", owner_id="USER_owner")

        kwargs = feed_repo_mock.find_by_owner.await_args.kwargs
        assert kwargs["owner_id"] == "USER_owner"
        assert kwargs["cursor"] is None
        assert kwargs["limit"] == POPUP_FEED_LIMIT
        assert kwargs["limit"] == 9  # popup spec 회귀 가드 (사용자 명시 9개)

    async def test_passes_visibilities_from_resolver(
        self, service, user_repo_mock, feed_repo_mock, visibilities_stub,
    ):
        """resolver 가 결정한 visibilities 부분집합을 그대로 repo 에 전달."""
        user_repo_mock.find_by_id_with_profile.return_value = make_user_with_profile_mock()
        feed_repo_mock.find_by_owner.return_value = []

        await service.get_popup(viewer_id="USER_v", owner_id="USER_owner")
        kwargs = feed_repo_mock.find_by_owner.await_args.kwargs
        assert kwargs["visibilities"] == visibilities_stub

    async def test_forwards_viewer_id_to_repo(
        self, service, user_repo_mock, feed_repo_mock,
    ):
        """popup 의 feed item 들에서 viewer 의 좋아요 여부가 정확히 합성되도록
        viewer_id 가 그대로 repo 까지 흘러가야 함. 빠지면 is_liked 가 항상 False 가 되는
        silent 회귀.
        """
        user_repo_mock.find_by_id_with_profile.return_value = make_user_with_profile_mock()
        feed_repo_mock.find_by_owner.return_value = []

        await service.get_popup(viewer_id="USER_v", owner_id="USER_owner")
        assert feed_repo_mock.find_by_owner.await_args.kwargs["viewer_id"] == "USER_v"

    async def test_response_propagates_is_liked_from_row(
        self, service, user_repo_mock, feed_repo_mock,
    ):
        """row.is_liked 가 popup 응답 DTO 까지 정확히 흘러가는지 — _to_feed_dto 누락 가드."""
        user_repo_mock.find_by_id_with_profile.return_value = make_user_with_profile_mock()
        feed_repo_mock.find_by_owner.return_value = [
            _mk_feed_row(post_id="FDP_a"),  # default is_liked=False
            FeedPostWithCounts(
                post=_mk_feed_row(post_id="FDP_b").post,
                like_count=0, comment_count=0, is_liked=True,
            ),
        ]

        result = await service.get_popup(viewer_id="USER_v", owner_id="USER_owner")
        assert result.feed_items[0].is_liked is False
        assert result.feed_items[1].is_liked is True


# ──────────────────── 본인 popup ────────────────────

@pytest.mark.unit
class TestSelfPopup:
    async def test_self_popup_passes_all_visibilities(
        self, service, user_repo_mock, feed_repo_mock, monkeypatch,
    ):
        """viewer == owner 일 때 access 가 모든 visibility 반환 → repo 에 그대로 전달."""
        user_repo_mock.find_by_id_with_profile.return_value = make_user_with_profile_mock(
            user_id="USER_a",
        )

        async def _resolve_self(session, *, viewer_id, owner_id):
            assert viewer_id == owner_id  # 본인 fast-path
            return list(FeedVisibility)
        monkeypatch.setattr(
            "app.domain.feed.service.feed_popup.resolve_viewer_visibilities", _resolve_self,
        )
        feed_repo_mock.find_by_owner.return_value = []

        result = await service.get_popup(viewer_id="USER_a", owner_id="USER_a")
        assert result.user_id == "USER_a"
        assert set(feed_repo_mock.find_by_owner.await_args.kwargs["visibilities"]) == set(FeedVisibility)
