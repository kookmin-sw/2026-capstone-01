"""메시지 편집 / 삭제 통합 테스트 (PHASE_2 #5).

실 Mongo 에 메시지를 쓴 뒤 편집/삭제가 문서에 반영되고, 히스토리 조회 시 삭제된
메시지는 content=None 으로 마스킹되는지까지 end-to-end 로 검증.
"""
import pytest_asyncio
import pytest

from app.domain.friend.model.friendship import Friendship, FriendshipStatus
from app.domain.chat.service.room import RoomService
from app.domain.chat.service.message_history import MessageHistoryService
from app.domain.chat.service.message import MessageService
from app.domain.chat.model.chat_message import MessageType


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


@pytest_asyncio.fixture
async def room_with_message(
    uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
    patch_external_clients,
):
    """그룹 방 + a 가 text 메시지 1 건 전송. (room_id, a, b, message_id, server_seq) 반환."""
    a, b, _ = await seed_users(3)
    await seed_friendship(a, b)
    room_svc = RoomService(
        uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
    )
    room = await room_svc.create_group_room(me_id=a, title="T", member_ids=[b])
    ack = await message_service.send_message(
        sender_user_id=a,
        sender_session_id="WS_A",
        room_id=room.chat_room_id,
        client_msg_id="cm-1",
        msg_type=MessageType.TEXT,
        content="hello",
    )
    return room.chat_room_id, a, b, ack.message_id, ack.server_seq


# ──────────────────────────────────────────────────────────────────
# 편집
# ──────────────────────────────────────────────────────────────────

class TestEditMessageFlow:
    async def test_edit_updates_mongo_and_fans_out(
        self, room_with_message, message_service, mongo_db, chat_fanout_stub,
        patch_external_clients,
    ):
        room_id, a, _, message_id, _ = room_with_message
        chat_fanout_stub.reset_mock()

        result = await message_service.edit_message(
            message_id=message_id, editor_user_id=a, editor_session_id="WS_A",
            new_content="edited!",
        )
        assert result["message_id"] == message_id
        assert result["content"] == "edited!"

        doc = await mongo_db.chat_message.find_one({"_id": message_id})
        assert doc["content"] == "edited!"
        assert doc["edited_at"] is not None
        assert doc["deleted_at"] is None

        chat_fanout_stub.fan_out_to_room.assert_awaited_once()
        payload = chat_fanout_stub.fan_out_to_room.call_args.args[1]
        assert payload["type"] == "message.updated"
        assert payload["content"] == "edited!"
        assert payload["message_id"] == message_id


    async def test_non_owner_cannot_edit(
        self, room_with_message, message_service, patch_external_clients,
    ):
        _, _, b, message_id, _ = room_with_message
        with pytest.raises(PermissionError):
            await message_service.edit_message(
                message_id=message_id, editor_user_id=b, editor_session_id="WS_B",
                new_content="hacked",
            )


    async def test_edit_after_soft_delete_rejected(
        self, room_with_message, message_service, patch_external_clients,
    ):
        """삭제된 메시지는 편집 불가."""
        _, a, _, message_id, _ = room_with_message
        await message_service.delete_message(
            message_id=message_id, deleter_user_id=a, deleter_session_id="WS_A",
        )
        with pytest.raises(ValueError, match="삭제된"):
            await message_service.edit_message(
                message_id=message_id, editor_user_id=a, editor_session_id="WS_A",
                new_content="zombie",
            )


# ──────────────────────────────────────────────────────────────────
# 삭제 (soft)
# ──────────────────────────────────────────────────────────────────

class TestDeleteMessageFlow:
    async def test_own_delete_masks_content_in_history(
        self, room_with_message, message_service, mongo_db, uow,
        patch_external_clients,
    ):
        room_id, a, _, message_id, server_seq = room_with_message

        await message_service.delete_message(
            message_id=message_id, deleter_user_id=a, deleter_session_id="WS_A",
        )

        # Mongo 상태
        doc = await mongo_db.chat_message.find_one({"_id": message_id})
        assert doc["deleted_at"] is not None
        assert doc["content"] is None

        # 히스토리 조회 → content 마스킹 (deleted_at 별도 포함)
        history = MessageHistoryService(uow=uow)
        page = await history.find_messages_after(
            me_id=a, room_id=room_id, after_server_seq=server_seq - 1, limit=10,
        )
        hit = next(m for m in page.messages if m.message_id == message_id)
        assert hit.content is None
        assert hit.deleted_at is not None


    async def test_group_creator_can_delete_others_message(
        self, uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
        patch_external_clients,
    ):
        a, b, _ = await seed_users(3)
        await seed_friendship(a, b)
        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await room_svc.create_group_room(me_id=a, title="T", member_ids=[b])
        # b 가 보낸 메시지를 방장 a 가 삭제
        ack = await message_service.send_message(
            sender_user_id=b, sender_session_id="WS_B", room_id=room.chat_room_id,
            client_msg_id="cm-b-1", msg_type=MessageType.TEXT, content="x",
        )
        await message_service.delete_message(
            message_id=ack.message_id, deleter_user_id=a, deleter_session_id="WS_A",
        )


    async def test_regular_member_cannot_delete_others(
        self, uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
        patch_external_clients,
    ):
        """creator 가 아닌 일반 멤버는 타인 메시지 삭제 불가."""
        a, b, c = await seed_users(3)
        await seed_friendship(a, b)
        await seed_friendship(a, c)
        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await room_svc.create_group_room(me_id=a, title="T", member_ids=[b, c])
        ack = await message_service.send_message(
            sender_user_id=b, sender_session_id="WS_B", room_id=room.chat_room_id,
            client_msg_id="cm-b-2", msg_type=MessageType.TEXT, content="x",
        )
        with pytest.raises(PermissionError):
            await message_service.delete_message(
                message_id=ack.message_id, deleter_user_id=c, deleter_session_id="WS_C",
            )


    async def test_system_message_cannot_be_deleted(
        self, uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
        mongo_db, patch_external_clients,
    ):
        a, b, _ = await seed_users(3)
        await seed_friendship(a, b)
        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await room_svc.create_group_room(me_id=a, title="T", member_ids=[b])

        # 생성 시 자동 발행된 system 메시지 찾기
        sys_doc = await mongo_db.chat_message.find_one(
            {"chat_room_id": room.chat_room_id, "type": "system"},
        )
        assert sys_doc is not None

        with pytest.raises(PermissionError, match="시스템"):
            await message_service.delete_message(
                message_id=sys_doc["_id"], deleter_user_id=a, deleter_session_id="WS_A",
            )


    async def test_second_delete_is_rejected(
        self, room_with_message, message_service, patch_external_clients,
    ):
        _, a, _, message_id, _ = room_with_message
        await message_service.delete_message(
            message_id=message_id, deleter_user_id=a, deleter_session_id="WS_A",
        )
        with pytest.raises(ValueError, match="이미 삭제"):
            await message_service.delete_message(
                message_id=message_id, deleter_user_id=a, deleter_session_id="WS_A",
            )
