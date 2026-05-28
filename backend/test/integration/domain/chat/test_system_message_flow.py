"""시스템 메시지 타임라인 통합 테스트 (PHASE_2 #2).

그룹 방 생성/초대/퇴장/강퇴 시 `MessageService.send_system_message` 가 실제 Mongo
`chat_message` 에 `type=system` 문서를 적재하고, `chat_room.last_message_*` 에도
반영되며, unread 는 증가하지 않는지 end-to-end 검증.

※ 방 관리 자체 흐름은 `test_room_group_flow.py` 에서 커버. 여기서는 타임라인
저장과 unread 미영향만.
"""
from sqlalchemy import select
import pytest_asyncio
import pytest

from app.domain.friend.model.friendship import Friendship, FriendshipStatus
from app.domain.chat.service.room import RoomService
from app.domain.chat.model.chat_room_member import ChatRoomMember
from app.domain.chat.model.chat_room import ChatRoom
from app.core.chat.redis_key import unread_key


pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def seed_friendship(session_factory):
    async def _seed(user_a: str, user_b: str) -> None:
        async with session_factory() as s:
            s.add(Friendship(
                requester_id=user_a,
                addressee_id=user_b,
                status=FriendshipStatus.ACCEPTED,
            ))
            await s.commit()
    return _seed


async def _fetch_system_messages(mongo_db, room_id: str) -> list[dict]:
    """방에 저장된 시스템 메시지 (server_seq 오름차순)."""
    cursor = mongo_db.chat_message.find(
        {"chat_room_id": room_id, "type": "system"}
    ).sort("server_seq", 1)
    return [doc async for doc in cursor]


class TestSystemMessageTimeline:
    async def test_create_group_writes_created_system_message(
        self, uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
        session_factory, mongo_db, patch_external_clients,
    ):
        a, b, _ = await seed_users(3)
        await seed_friendship(a, b)

        service = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await service.create_group_room(
            me_id=a, title="T", member_ids=[b],
        )

        msgs = await _fetch_system_messages(mongo_db, room.chat_room_id)
        assert len(msgs) == 1
        m = msgs[0]
        assert m["sender_id"] is None
        assert m["content"] == {"action": "created", "actor_id": a}
        assert m["server_seq"] >= 1

        # chat_room.last_message_* 에 해당 seq 반영
        async with session_factory() as s:
            fresh = await s.get(ChatRoom, room.chat_room_id)
            assert fresh.last_message_server_seq == m["server_seq"]
            assert fresh.last_message_id == m["_id"]


    async def test_invite_writes_join_system_message_with_target_ids(
        self, uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
        mongo_db, patch_external_clients,
    ):
        a, b, c = await seed_users(3)
        await seed_friendship(a, b)
        await seed_friendship(a, c)

        service = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await service.create_group_room(
            me_id=a, title="T", member_ids=[b],
        )
        # 방 생성 시점의 "created" 메시지는 이미 1건 있음
        await service.invite_members(
            me_id=a, room_id=room.chat_room_id, user_ids=[c],
        )

        msgs = await _fetch_system_messages(mongo_db, room.chat_room_id)
        actions = [m["content"]["action"] for m in msgs]
        assert actions == ["created", "join"]
        assert msgs[-1]["content"]["target_ids"] == [c]
        assert msgs[-1]["content"]["actor_id"] == a


    async def test_leave_writes_leave_system_message(
        self, uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
        mongo_db, patch_external_clients,
    ):
        a, b, _ = await seed_users(3)
        await seed_friendship(a, b)

        service = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await service.create_group_room(
            me_id=a, title="T", member_ids=[b],
        )
        await service.leave_room(me_id=b, room_id=room.chat_room_id)

        msgs = await _fetch_system_messages(mongo_db, room.chat_room_id)
        assert [m["content"]["action"] for m in msgs] == ["created", "leave"]
        assert msgs[-1]["content"]["actor_id"] == b
        assert "target_ids" not in msgs[-1]["content"]


    async def test_kick_writes_kick_system_message_with_target(
        self, uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
        mongo_db, patch_external_clients,
    ):
        a, b, _ = await seed_users(3)
        await seed_friendship(a, b)

        service = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await service.create_group_room(
            me_id=a, title="T", member_ids=[b],
        )
        await service.kick_member(
            me_id=a, room_id=room.chat_room_id, target_user_id=b,
        )

        msgs = await _fetch_system_messages(mongo_db, room.chat_room_id)
        assert [m["content"]["action"] for m in msgs] == ["created", "kick"]
        assert msgs[-1]["content"]["actor_id"] == a
        assert msgs[-1]["content"]["target_ids"] == [b]


    async def test_system_messages_do_not_bump_unread(
        self, uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
        redis_hot, patch_external_clients,
    ):
        """PHASE_2 H3: 시스템 메시지는 unread 를 증가시키지 않는다.

        방 생성 직후 `unread:{uid}` 는 0 으로 세팅되어 있어야 하고, 이후 invite/leave
        시스템 메시지가 추가로 발행되어도 다른 멤버의 unread 값이 그대로여야 한다.
        """
        a, b, c = await seed_users(3)
        await seed_friendship(a, b)
        await seed_friendship(a, c)

        service = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await service.create_group_room(
            me_id=a, title="T", member_ids=[b],
        )

        # 방 생성 시 unread 전원 0
        for uid in (a, b):
            raw = await redis_hot.hget(unread_key(uid), room.chat_room_id)
            assert raw == "0"

        # c 초대 → join 시스템 메시지가 발행되지만 a/b 의 unread 는 그대로 0
        await service.invite_members(
            me_id=a, room_id=room.chat_room_id, user_ids=[c],
        )
        for uid in (a, b):
            raw = await redis_hot.hget(unread_key(uid), room.chat_room_id)
            assert raw == "0", f"{uid} 의 unread 가 시스템 메시지로 증가함"
