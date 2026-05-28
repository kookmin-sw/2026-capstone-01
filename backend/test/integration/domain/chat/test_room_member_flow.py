"""그룹 방 참여자 / 초대 가능 친구 목록 통합 테스트.

실제 Postgres 를 통해 ChatRoomMemberRepository.find_active_member_users 의 join +
order_by 동작과 MessageHistoryService 의 권한/필터 분기를 함께 검증한다. Redis/Mongo
는 방 생성 부수효과를 위해 stub 사용 (`patch_external_clients` 재사용).
"""
import pytest_asyncio
import pytest

from app.domain.friend.model.friendship import Friendship, FriendshipStatus
from app.domain.chat.service.room import RoomService
from app.domain.chat.service.message_history import MessageHistoryService
from app.domain.chat.service.exception import ChatRoomNotFoundError
from app.domain.chat.model.chat_room_member import ChatRoomMember
from app.domain.auth.model.user_detail_inform import UserDetailInform


pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def seed_friendship(session_factory):
    """두 유저를 ACCEPTED 친구로 맺어주는 헬퍼."""
    async def _seed(user_a: str, user_b: str) -> None:
        async with session_factory() as s:
            s.add(Friendship(
                requester_id=user_a,
                addressee_id=user_b,
                status=FriendshipStatus.ACCEPTED,
            ))
            await s.commit()
    return _seed


@pytest_asyncio.fixture
async def set_profile_image(session_factory):
    """seed_users 가 만든 UserDetailInform 의 profile_image_url 을 갱신."""
    async def _set(user_id: str, url: str) -> None:
        async with session_factory() as s:
            detail = await s.get(UserDetailInform, user_id)
            detail.profile_image_url = url
            await s.commit()
    return _set


# ──────────────────────────────────────────────────────────────────
# list_room_members
# ──────────────────────────────────────────────────────────────────

class TestListRoomMembersFlow:
    async def test_returns_active_members_with_profile_in_join_order(
        self, uow, seed_users, seed_friendship, set_profile_image,
        chat_fanout_stub, message_service, patch_external_clients,
    ):
        a, b, c = await seed_users(3)
        await seed_friendship(a, b)
        await seed_friendship(a, c)
        await set_profile_image(b, "https://cdn.example.com/b.jpg")

        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await room_svc.create_group_room(
            me_id=a, title="T", member_ids=[b, c],
        )

        history = MessageHistoryService(uow=uow)
        result = await history.list_room_members(me_id=a, room_id=room.chat_room_id)

        assert len(result.items) == 3
        ids = {m.user_id for m in result.items}
        assert ids == {a, b, c}
        by_id = {m.user_id: m for m in result.items}
        assert by_id[b].profile_image_url == "https://cdn.example.com/b.jpg"
        assert by_id[a].profile_image_url is None  # set 하지 않음


    async def test_excludes_left_members(
        self, uow, seed_users, seed_friendship, chat_fanout_stub,
        message_service, patch_external_clients, session_factory,
    ):
        a, b, c = await seed_users(3)
        await seed_friendship(a, b)
        await seed_friendship(a, c)

        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await room_svc.create_group_room(
            me_id=a, title="T", member_ids=[b, c],
        )

        # b 를 탈퇴 처리
        await room_svc.leave_room(me_id=b, room_id=room.chat_room_id)

        history = MessageHistoryService(uow=uow)
        result = await history.list_room_members(me_id=a, room_id=room.chat_room_id)

        assert {m.user_id for m in result.items} == {a, c}


    async def test_non_member_raises_permission_error(
        self, uow, seed_users, seed_friendship, chat_fanout_stub,
        message_service, patch_external_clients,
    ):
        a, b, c = await seed_users(3)
        await seed_friendship(a, b)

        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await room_svc.create_group_room(me_id=a, title="T", member_ids=[b])

        history = MessageHistoryService(uow=uow)
        with pytest.raises(PermissionError):
            await history.list_room_members(me_id=c, room_id=room.chat_room_id)


    async def test_direct_room_raises_value_error(
        self, uow, seed_users, chat_fanout_stub, message_service,
        patch_external_clients,
    ):
        a, b, _ = await seed_users(3)
        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        direct = await room_svc.create_direct_room(me_id=a, peer_user_id=b)

        history = MessageHistoryService(uow=uow)
        with pytest.raises(ValueError, match="그룹 방"):
            await history.list_room_members(me_id=a, room_id=direct.chat_room_id)


    async def test_unknown_room_raises_not_found(self, uow):
        history = MessageHistoryService(uow=uow)
        with pytest.raises(ChatRoomNotFoundError):
            await history.list_room_members(me_id="U_X", room_id="CR_unknown")


# ──────────────────────────────────────────────────────────────────
# list_invitable_friends
# ──────────────────────────────────────────────────────────────────

class TestListInvitableFriendsFlow:
    async def test_returns_friends_not_yet_in_room(
        self, uow, seed_users, seed_friendship, set_profile_image,
        chat_fanout_stub, message_service, patch_external_clients,
    ):
        a, b, c, d = await seed_users(4)
        await seed_friendship(a, b)
        await seed_friendship(a, c)
        await seed_friendship(a, d)
        await set_profile_image(c, "https://cdn.example.com/c.jpg")

        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        # b 만 방에 초대 → c, d 가 invitable
        room = await room_svc.create_group_room(me_id=a, title="T", member_ids=[b])

        history = MessageHistoryService(uow=uow)
        result = await history.list_invitable_friends(
            me_id=a, room_id=room.chat_room_id,
        )

        ids = {m.user_id for m in result.items}
        assert ids == {c, d}
        by_id = {m.user_id: m for m in result.items}
        assert by_id[c].profile_image_url == "https://cdn.example.com/c.jpg"


    async def test_left_friend_is_invitable_again(
        self, uow, seed_users, seed_friendship, chat_fanout_stub,
        message_service, patch_external_clients, session_factory,
    ):
        """탈퇴(is_left=true) 한 친구는 활성 멤버에서 빠져 다시 초대 가능."""
        a, b, _ = await seed_users(3)
        await seed_friendship(a, b)

        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await room_svc.create_group_room(me_id=a, title="T", member_ids=[b])
        await room_svc.leave_room(me_id=b, room_id=room.chat_room_id)

        history = MessageHistoryService(uow=uow)
        result = await history.list_invitable_friends(
            me_id=a, room_id=room.chat_room_id,
        )
        assert {m.user_id for m in result.items} == {b}


    async def test_no_friends_returns_empty(
        self, uow, seed_users, seed_friendship, chat_fanout_stub,
        message_service, patch_external_clients,
    ):
        a, b, _ = await seed_users(3)
        await seed_friendship(a, b)

        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await room_svc.create_group_room(me_id=a, title="T", member_ids=[b])

        # b 외에 친구가 없고 b 는 이미 멤버 → invitable 없음
        history = MessageHistoryService(uow=uow)
        result = await history.list_invitable_friends(
            me_id=a, room_id=room.chat_room_id,
        )
        assert result.items == []


    async def test_non_member_raises_permission_error(
        self, uow, seed_users, seed_friendship, chat_fanout_stub,
        message_service, patch_external_clients,
    ):
        a, b, c = await seed_users(3)
        await seed_friendship(a, b)

        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await room_svc.create_group_room(me_id=a, title="T", member_ids=[b])

        history = MessageHistoryService(uow=uow)
        with pytest.raises(PermissionError):
            await history.list_invitable_friends(me_id=c, room_id=room.chat_room_id)


    async def test_direct_room_raises_value_error(
        self, uow, seed_users, chat_fanout_stub, message_service,
        patch_external_clients,
    ):
        a, b, _ = await seed_users(3)
        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        direct = await room_svc.create_direct_room(me_id=a, peer_user_id=b)

        history = MessageHistoryService(uow=uow)
        with pytest.raises(ValueError, match="그룹 방"):
            await history.list_invitable_friends(me_id=a, room_id=direct.chat_room_id)
