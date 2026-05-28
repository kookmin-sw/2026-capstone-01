"""FriendDetailService 통합 테스트 — 실 DB 로 friendship · block · profile 조합 검증."""

import pytest

from app.domain.friend.service.user_block import UserBlockService
from app.domain.friend.service.friendship import FriendshipService
from app.domain.friend.service.friend_detail import FriendDetailService, UserNotFoundError
from app.domain.friend.model.friendship import FriendshipStatus
from app.domain.auth.model.user_travel_style import TravelStyle, UserTravelStyle


pytestmark = pytest.mark.integration


class TestFriendDetailFlow:
    async def test_returns_public_profile_without_sensitive_fields(
        self, uow, seed_users, session_factory,
    ):
        a, b, _ = await seed_users(3)

        # b 에 travel_style 2건 추가
        async with session_factory() as s:
            s.add(UserTravelStyle(user_id=b, style=TravelStyle.FOOD_TOUR))
            s.add(UserTravelStyle(user_id=b, style=TravelStyle.ACTIVITY))
            await s.commit()

        service = FriendDetailService(uow=uow)
        result = await service.get_friend_detail(viewer_id=a, peer_id=b)

        # 공개 프로필만 노출
        assert result.user_id == b
        assert result.user_name == "user1"
        assert set(result.travel_styles) == {TravelStyle.FOOD_TOUR, TravelStyle.ACTIVITY}

        # DTO 자체에 민감 필드가 없음을 확인 (auth_provider / status / email / phone_number)
        assert not hasattr(result, "email")
        assert not hasattr(result, "phone_number")
        assert not hasattr(result, "auth_provider")
        assert not hasattr(result, "status")


    async def test_reflects_pending_request_sent(self, uow, seed_users):
        a, b, _ = await seed_users(3)

        friendship_service = FriendshipService(uow=uow)
        await friendship_service.send_request(requester_id=a, addressee_id=b)

        detail_service = FriendDetailService(uow=uow)
        result = await detail_service.get_friend_detail(viewer_id=a, peer_id=b)

        assert result.friendship_status == FriendshipStatus.PENDING
        assert result.is_requester is True
        assert result.i_blocked_peer is False


    async def test_reflects_accepted_friendship(self, uow, seed_users):
        a, b, _ = await seed_users(3)

        friendship_service = FriendshipService(uow=uow)
        created = await friendship_service.send_request(requester_id=a, addressee_id=b)
        await friendship_service.accept_request(friendship_id=created.friendship_id, user_id=b)

        detail_service = FriendDetailService(uow=uow)
        result = await detail_service.get_friend_detail(viewer_id=a, peer_id=b)

        assert result.friendship_status == FriendshipStatus.ACCEPTED
        assert result.friendship_id == created.friendship_id


    async def test_block_removes_friendship_and_sets_flag(self, uow, seed_users):
        """차단 시 friendship 은 삭제되고 i_blocked_peer 만 true 로 남음."""
        from unittest.mock import AsyncMock, MagicMock
        a, b, _ = await seed_users(3)

        friendship_service = FriendshipService(uow=uow)
        created = await friendship_service.send_request(requester_id=a, addressee_id=b)
        await friendship_service.accept_request(friendship_id=created.friendship_id, user_id=b)

        block_cache_stub = MagicMock()
        block_cache_stub.invalidate_block_cache = AsyncMock()
        block_service = UserBlockService(uow=uow, block_cache_service=block_cache_stub)
        await block_service.block_user(user_id=a, target_user_id=b)

        detail_service = FriendDetailService(uow=uow)
        result = await detail_service.get_friend_detail(viewer_id=a, peer_id=b)

        assert result.i_blocked_peer is True
        assert result.friendship_id is None
        assert result.friendship_status is None
        assert result.is_requester is None


    async def test_raises_user_not_found_for_missing_peer(self, uow, seed_users):
        (a,) = await seed_users(1)
        service = FriendDetailService(uow=uow)

        with pytest.raises(UserNotFoundError):
            await service.get_friend_detail(viewer_id=a, peer_id="USER_ghost")


    async def test_self_query_returns_own_profile(self, uow, seed_users):
        (a,) = await seed_users(1)
        service = FriendDetailService(uow=uow)

        result = await service.get_friend_detail(viewer_id=a, peer_id=a)

        assert result.user_id == a
        assert result.friendship_id is None
        assert result.friendship_status is None
        assert result.is_requester is None
        assert result.i_blocked_peer is False
