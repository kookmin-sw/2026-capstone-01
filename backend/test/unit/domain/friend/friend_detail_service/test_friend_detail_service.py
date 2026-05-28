from test.unit.domain.friend.friend_detail_service.model_factory import (
    FriendshipFactory,
    UserFactory,
)
import pytest

from app.domain.friend.service.friend_detail import UserNotFoundError
from app.domain.friend.model.friendship import FriendshipStatus
from app.domain.auth.model.user_travel_style import TravelStyle


@pytest.mark.unit
class TestGetFriendDetail:
    """Tests for FriendDetailService.get_friend_detail."""

    # ──────────────────── 에러 경로 ────────────────────

    async def test_raises_user_not_found_when_peer_missing(self, service, user_repo_mock):
        user_repo_mock.find_by_id_with_profile.return_value = None

        with pytest.raises(UserNotFoundError, match="존재하지 않는 유저"):
            await service.get_friend_detail(viewer_id="USER_a", peer_id="USER_b")


    async def test_raises_value_error_when_profile_incomplete(self, service, user_repo_mock):
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create(
            user_id="USER_b", detail=None,
        )

        with pytest.raises(ValueError, match="2차 회원가입이 완료되지 않은") as exc_info:
            await service.get_friend_detail(viewer_id="USER_a", peer_id="USER_b")

        # UserNotFoundError 와 구분되어야 함 (404 가 아닌 400 으로 매핑)
        assert not isinstance(exc_info.value, UserNotFoundError)

    # ──────────────────── 관계 조합 ────────────────────

    async def test_returns_profile_with_no_relationship_no_block(
        self, service, user_repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create(
            user_id="USER_b",
            user_name="영희",
            age=28,
            travel_styles=[TravelStyle.FOOD_TOUR, TravelStyle.ACTIVITY],
        )
        friendship_repo_mock.find_between.return_value = None
        block_repo_mock.has_blocker_blocked.return_value = False

        result = await service.get_friend_detail(viewer_id="USER_a", peer_id="USER_b")

        assert result.user_id == "USER_b"
        assert result.user_name == "영희"
        assert result.age == 28
        assert result.travel_styles == [TravelStyle.FOOD_TOUR, TravelStyle.ACTIVITY]
        assert result.friendship_id is None
        assert result.friendship_status is None
        assert result.is_requester is None
        assert result.i_blocked_peer is False


    async def test_returns_pending_as_requester(
        self, service, user_repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create(user_id="USER_b")
        friendship_repo_mock.find_between.return_value = FriendshipFactory.create(
            friendship_id="FS_1",
            requester_id="USER_a",  # viewer가 보낸 쪽
            addressee_id="USER_b",
            status=FriendshipStatus.PENDING,
        )
        block_repo_mock.has_blocker_blocked.return_value = False

        result = await service.get_friend_detail(viewer_id="USER_a", peer_id="USER_b")

        assert result.friendship_id == "FS_1"
        assert result.friendship_status == FriendshipStatus.PENDING
        assert result.is_requester is True


    async def test_returns_pending_as_addressee(
        self, service, user_repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create(user_id="USER_b")
        friendship_repo_mock.find_between.return_value = FriendshipFactory.create(
            requester_id="USER_b",  # 상대가 보낸 요청
            addressee_id="USER_a",
            status=FriendshipStatus.PENDING,
        )
        block_repo_mock.has_blocker_blocked.return_value = False

        result = await service.get_friend_detail(viewer_id="USER_a", peer_id="USER_b")

        assert result.friendship_status == FriendshipStatus.PENDING
        assert result.is_requester is False


    async def test_returns_accepted_friendship(
        self, service, user_repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create(user_id="USER_b")
        friendship_repo_mock.find_between.return_value = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.ACCEPTED,
        )
        block_repo_mock.has_blocker_blocked.return_value = False

        result = await service.get_friend_detail(viewer_id="USER_a", peer_id="USER_b")

        assert result.friendship_status == FriendshipStatus.ACCEPTED
        assert result.is_requester is True


    async def test_returns_rejected_friendship(
        self, service, user_repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create(user_id="USER_b")
        friendship_repo_mock.find_between.return_value = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.REJECTED,
        )
        block_repo_mock.has_blocker_blocked.return_value = False

        result = await service.get_friend_detail(viewer_id="USER_a", peer_id="USER_b")

        assert result.friendship_status == FriendshipStatus.REJECTED
        assert result.is_requester is True


    async def test_returns_i_blocked_peer_flag(
        self, service, user_repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create(user_id="USER_b")
        # 실제 플로우상 차단 시 friendship 은 정리되지만, 서비스 입장에선 독립 조회
        friendship_repo_mock.find_between.return_value = None
        block_repo_mock.has_blocker_blocked.return_value = True

        result = await service.get_friend_detail(viewer_id="USER_a", peer_id="USER_b")

        assert result.i_blocked_peer is True
        assert result.friendship_id is None


    async def test_block_check_is_directional_viewer_to_peer(
        self, service, user_repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        """service 는 viewer→peer 방향만 조회 (peer→viewer 방향은 더 이상 노출 안 함)."""
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create(user_id="USER_b")
        friendship_repo_mock.find_between.return_value = None
        block_repo_mock.has_blocker_blocked.return_value = False

        await service.get_friend_detail(viewer_id="USER_a", peer_id="USER_b")

        block_repo_mock.has_blocker_blocked.assert_awaited_once_with("USER_a", "USER_b")

    # ──────────────────── 자기 자신 조회 (허용) ────────────────────

    async def test_allows_self_query_with_null_relationship(
        self, service, user_repo_mock, friendship_repo_mock, block_repo_mock,
    ):
        """viewer == peer 케이스는 막지 않음 — 공개 프로필 + 관계 필드 전부 null/false."""
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create(user_id="USER_a")
        friendship_repo_mock.find_between.return_value = None
        block_repo_mock.has_blocker_blocked.return_value = False

        result = await service.get_friend_detail(viewer_id="USER_a", peer_id="USER_a")

        assert result.user_id == "USER_a"
        assert result.friendship_id is None
        assert result.friendship_status is None
        assert result.is_requester is None
        assert result.i_blocked_peer is False
