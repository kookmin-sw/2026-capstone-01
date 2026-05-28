from test.unit.domain.friend.search_service.model_factory import (
    FriendshipFactory,
    UserFactory,
)
import pytest

from app.domain.friend.repository.search import PAGE_SIZE
from app.domain.friend.model.friendship import FriendshipStatus
from app.domain.auth.model.user_travel_style import TravelStyle


@pytest.mark.unit
class TestSearchKeywordValidation:
    """입력 keyword 정규화 + 빈 문자열 방어."""

    async def test_raises_value_error_on_empty_keyword(self, service):
        with pytest.raises(ValueError, match="검색어를 입력해주세요"):
            await service.search(viewer_id="USER_a", keyword="")


    async def test_raises_value_error_on_whitespace_only(self, service):
        with pytest.raises(ValueError, match="검색어를 입력해주세요"):
            await service.search(viewer_id="USER_a", keyword="   ")


    async def test_raises_value_error_on_tab_and_newline_only(self, service):
        with pytest.raises(ValueError, match="검색어를 입력해주세요"):
            await service.search(viewer_id="USER_a", keyword="\t\n")


    async def test_strips_leading_trailing_whitespace_before_search(
        self, service, search_repo_mock,
    ):
        search_repo_mock.search_active_users.return_value = []

        await service.search(viewer_id="USER_a", keyword="  조현상  ")

        search_repo_mock.search_active_users.assert_awaited_once_with(
            viewer_id="USER_a", keyword="조현상", cursor=None,
        )


@pytest.mark.unit
class TestSearchEmptyResult:
    """매칭되는 유저가 없을 때 동작."""

    async def test_returns_empty_items_and_null_cursor(self, service, search_repo_mock):
        search_repo_mock.search_active_users.return_value = []

        result = await service.search(viewer_id="USER_a", keyword="nobody")

        assert result.items == []
        assert result.next_cursor is None


    async def test_friendship_lookup_called_with_empty_list(
        self, service, search_repo_mock, friendship_repo_mock,
    ):
        """결과 0건이어도 friendship_repo 는 빈 리스트로 호출 — 쿼리 자체는 스킵."""
        search_repo_mock.search_active_users.return_value = []

        await service.search(viewer_id="USER_a", keyword="nobody")

        friendship_repo_mock.find_friendships_with.assert_awaited_once_with("USER_a", [])


@pytest.mark.unit
class TestSearchDtoMapping:
    """user → FriendSearchData 변환 검증."""

    async def test_no_friendship_yields_null_status_and_is_requester(
        self, service, search_repo_mock, friendship_repo_mock,
    ):
        peer = UserFactory.create(
            user_id="USER_b",
            user_name="영희",
            nationality="KR",
            travel_styles=[TravelStyle.FOOD_TOUR],
        )
        peer.detail.profile_image_url = "https://cdn/x.png"
        search_repo_mock.search_active_users.return_value = [peer]
        friendship_repo_mock.find_friendships_with.return_value = {}

        result = await service.search(viewer_id="USER_a", keyword="영")

        assert len(result.items) == 1
        item = result.items[0]
        assert item.user_id == "USER_b"
        assert item.user_name == "영희"
        assert item.nationality == "KR"
        assert item.travel_styles == [TravelStyle.FOOD_TOUR]
        assert item.profile_image_url == "https://cdn/x.png"
        assert item.friendship_status is None
        assert item.is_requester is None
        assert item.i_blocked_peer is False


    async def test_pending_as_requester_sets_is_requester_true(
        self, service, search_repo_mock, friendship_repo_mock,
    ):
        peer = UserFactory.create(user_id="USER_b")
        friendship = FriendshipFactory.create(
            requester_id="USER_a",   # viewer 가 보낸 쪽
            addressee_id="USER_b",
            status=FriendshipStatus.PENDING,
        )
        search_repo_mock.search_active_users.return_value = [peer]
        friendship_repo_mock.find_friendships_with.return_value = {"USER_b": friendship}

        result = await service.search(viewer_id="USER_a", keyword="b")

        item = result.items[0]
        assert item.friendship_status == FriendshipStatus.PENDING
        assert item.is_requester is True


    async def test_pending_as_addressee_sets_is_requester_false(
        self, service, search_repo_mock, friendship_repo_mock,
    ):
        peer = UserFactory.create(user_id="USER_b")
        friendship = FriendshipFactory.create(
            requester_id="USER_b",   # 상대가 보낸 요청
            addressee_id="USER_a",
            status=FriendshipStatus.PENDING,
        )
        search_repo_mock.search_active_users.return_value = [peer]
        friendship_repo_mock.find_friendships_with.return_value = {"USER_b": friendship}

        result = await service.search(viewer_id="USER_a", keyword="b")

        item = result.items[0]
        assert item.friendship_status == FriendshipStatus.PENDING
        assert item.is_requester is False


    async def test_accepted_yields_null_is_requester(
        self, service, search_repo_mock, friendship_repo_mock,
    ):
        """ACCEPTED 에선 is_requester 가 의미 없으므로 None — spec 정의."""
        peer = UserFactory.create(user_id="USER_b")
        friendship = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.ACCEPTED,
        )
        search_repo_mock.search_active_users.return_value = [peer]
        friendship_repo_mock.find_friendships_with.return_value = {"USER_b": friendship}

        result = await service.search(viewer_id="USER_a", keyword="b")

        item = result.items[0]
        assert item.friendship_status == FriendshipStatus.ACCEPTED
        assert item.is_requester is None


    async def test_rejected_yields_null_is_requester(
        self, service, search_repo_mock, friendship_repo_mock,
    ):
        peer = UserFactory.create(user_id="USER_b")
        friendship = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.REJECTED,
        )
        search_repo_mock.search_active_users.return_value = [peer]
        friendship_repo_mock.find_friendships_with.return_value = {"USER_b": friendship}

        result = await service.search(viewer_id="USER_a", keyword="b")

        item = result.items[0]
        assert item.friendship_status == FriendshipStatus.REJECTED
        assert item.is_requester is None


    async def test_i_blocked_peer_always_false(
        self, service, search_repo_mock, friendship_repo_mock,
    ):
        """검색은 차단 유저를 자동 제외하므로 결과 항목의 i_blocked_peer 는 항상 False."""
        peer = UserFactory.create(user_id="USER_b")
        search_repo_mock.search_active_users.return_value = [peer]
        friendship_repo_mock.find_friendships_with.return_value = {}

        result = await service.search(viewer_id="USER_a", keyword="b")

        assert result.items[0].i_blocked_peer is False


    async def test_mixed_results_with_partial_friendship_mapping(
        self, service, search_repo_mock, friendship_repo_mock,
    ):
        """일부 유저만 friendship 이 있고, 나머지는 None — 매핑이 dict.get() 으로 정확히 분기."""
        peer_b = UserFactory.create(user_id="USER_b")
        peer_c = UserFactory.create(user_id="USER_c")
        peer_d = UserFactory.create(user_id="USER_d")
        friendship_b = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.ACCEPTED,
        )
        friendship_d = FriendshipFactory.create(
            requester_id="USER_d",
            addressee_id="USER_a",
            status=FriendshipStatus.PENDING,
        )
        search_repo_mock.search_active_users.return_value = [peer_b, peer_c, peer_d]
        friendship_repo_mock.find_friendships_with.return_value = {
            "USER_b": friendship_b,
            "USER_d": friendship_d,
        }

        result = await service.search(viewer_id="USER_a", keyword="x")

        by_id = {item.user_id: item for item in result.items}
        assert by_id["USER_b"].friendship_status == FriendshipStatus.ACCEPTED
        assert by_id["USER_b"].is_requester is None
        assert by_id["USER_c"].friendship_status is None
        assert by_id["USER_c"].is_requester is None
        assert by_id["USER_d"].friendship_status == FriendshipStatus.PENDING
        assert by_id["USER_d"].is_requester is False  # peer 가 요청자


@pytest.mark.unit
class TestSearchPagination:
    """커서 페이지네이션 / next_cursor 계산."""

    async def test_next_cursor_is_last_user_id_when_page_full(
        self, service, search_repo_mock, friendship_repo_mock,
    ):
        users = [UserFactory.create(user_id=f"USER_{i:03d}") for i in range(PAGE_SIZE)]
        search_repo_mock.search_active_users.return_value = users
        friendship_repo_mock.find_friendships_with.return_value = {}

        result = await service.search(viewer_id="USER_viewer", keyword="x")

        assert len(result.items) == PAGE_SIZE
        assert result.next_cursor == users[-1].user_id


    async def test_next_cursor_null_on_partial_page(
        self, service, search_repo_mock, friendship_repo_mock,
    ):
        users = [UserFactory.create() for _ in range(PAGE_SIZE - 1)]
        search_repo_mock.search_active_users.return_value = users
        friendship_repo_mock.find_friendships_with.return_value = {}

        result = await service.search(viewer_id="USER_viewer", keyword="x")

        assert len(result.items) == PAGE_SIZE - 1
        assert result.next_cursor is None


    async def test_cursor_argument_passed_through_to_repo(
        self, service, search_repo_mock,
    ):
        search_repo_mock.search_active_users.return_value = []

        await service.search(viewer_id="USER_a", keyword="x", cursor="USER_xyz")

        search_repo_mock.search_active_users.assert_awaited_once_with(
            viewer_id="USER_a", keyword="x", cursor="USER_xyz",
        )


@pytest.mark.unit
class TestSearchFriendshipBatchLookup:
    """N+1 방지 — peer_ids 를 한 번에 friendship_repo 로 조회."""

    async def test_friendship_lookup_called_once_with_all_peer_ids(
        self, service, search_repo_mock, friendship_repo_mock,
    ):
        users = [
            UserFactory.create(user_id="USER_b"),
            UserFactory.create(user_id="USER_c"),
            UserFactory.create(user_id="USER_d"),
        ]
        search_repo_mock.search_active_users.return_value = users
        friendship_repo_mock.find_friendships_with.return_value = {}

        await service.search(viewer_id="USER_a", keyword="x")

        friendship_repo_mock.find_friendships_with.assert_awaited_once_with(
            "USER_a", ["USER_b", "USER_c", "USER_d"],
        )


    async def test_peer_ids_preserve_repo_order(
        self, service, search_repo_mock, friendship_repo_mock,
    ):
        """repo 의 정렬 순서를 유지해 next_cursor 가 마지막 아이템 user_id 와 일치하도록."""
        users = [
            UserFactory.create(user_id="USER_z"),
            UserFactory.create(user_id="USER_a"),
            UserFactory.create(user_id="USER_m"),
        ]
        search_repo_mock.search_active_users.return_value = users
        friendship_repo_mock.find_friendships_with.return_value = {}

        result = await service.search(viewer_id="USER_viewer", keyword="x")

        assert [it.user_id for it in result.items] == ["USER_z", "USER_a", "USER_m"]
