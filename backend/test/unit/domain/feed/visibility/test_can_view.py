"""`can_view` 순수 함수 회귀 — visibility 결정의 단일 진입점.

매트릭스 (8 + α 케이스):
    is_blocked=True 면 무조건 False (5 변종)
    viewer == owner 면 무조건 True (3 visibility × 2 friend = 6 변종 → 대표 3)
    viewer != owner:
        PUBLIC                    → True
        FRIENDS  + is_friend      → True
        FRIENDS  + not is_friend  → False
        PRIVATE                   → False (친구 여부 무관)

`_resolve_viewer_visibilities` 가 enum 에 대해 iterate 해 본 함수를 호출하므로,
규칙이 깨지면 user feed 페이지네이션의 visibility IN-list 가 통째로 잘못 구성된다.
"""
import pytest

from app.domain.feed.service.visibility import can_view
from app.domain.feed.model.feed_post import FeedVisibility


def _call(visibility, viewer="USER_v", owner="USER_o", is_friend=False, is_blocked=False):
    return can_view(
        viewer_id=viewer,
        owner_id=owner,
        image_visibility=visibility,
        is_friend=is_friend,
        is_blocked_either_way=is_blocked,
    )


@pytest.mark.unit
class TestBlockedAlwaysFalse:
    """차단 우선 — 다른 모든 조건 무관하게 False."""

    @pytest.mark.parametrize("visibility", list(FeedVisibility))
    @pytest.mark.parametrize("is_friend", [True, False])
    def test_blocked_returns_false(self, visibility, is_friend):
        assert _call(visibility, is_friend=is_friend, is_blocked=True) is False


    def test_blocked_overrides_self(self):
        """본인이라도 차단 (이론적으로는 발생 안 하지만 함수 contract 차원) 이면 False."""
        assert _call(
            FeedVisibility.PRIVATE,
            viewer="USER_a", owner="USER_a",
            is_blocked=True,
        ) is False


@pytest.mark.unit
class TestSelfAlwaysTrue:
    """viewer == owner 면 모든 visibility 허용 (친구 여부 무관)."""

    @pytest.mark.parametrize("visibility", list(FeedVisibility))
    def test_self_can_view_all_visibilities(self, visibility):
        assert _call(visibility, viewer="USER_x", owner="USER_x") is True


@pytest.mark.unit
class TestNonSelfPublic:
    @pytest.mark.parametrize("is_friend", [True, False])
    def test_public_visible_regardless_of_friendship(self, is_friend):
        assert _call(FeedVisibility.PUBLIC, is_friend=is_friend) is True


@pytest.mark.unit
class TestNonSelfFriends:
    def test_friend_can_view(self):
        assert _call(FeedVisibility.FRIENDS, is_friend=True) is True


    def test_non_friend_cannot_view(self):
        assert _call(FeedVisibility.FRIENDS, is_friend=False) is False


@pytest.mark.unit
class TestNonSelfPrivate:
    @pytest.mark.parametrize("is_friend", [True, False])
    def test_private_never_visible_to_others(self, is_friend):
        """PRIVATE 은 본인 외 누구도 못 봄 — 친구라도 안 됨."""
        assert _call(FeedVisibility.PRIVATE, is_friend=is_friend) is False
