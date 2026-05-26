"""RoomService.mark_read 통합 테스트 (PHASE_2 #3).

RDB 의 `GREATEST(COALESCE(last_read, 0), :new_seq)` 규약이 실제 Postgres 에서
작동하는지 + Redis unread 리셋 + fan-out 이벤트 구조 end-to-end 검증.
"""
from sqlalchemy import select
import pytest_asyncio
import pytest

from app.domain.friend.model.friendship import Friendship, FriendshipStatus
from app.domain.chat.service.room import RoomService
from app.domain.chat.service.exception import ChatRoomNotFoundError
from app.domain.chat.model.chat_room_member import ChatRoomMember
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


class TestMarkReadFlow:
    async def test_sets_last_read_and_resets_unread(
        self, uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
        session_factory, redis_hot, patch_external_clients,
    ):
        a, b, _ = await seed_users(3)
        await seed_friendship(a, b)

        service = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await service.create_group_room(me_id=a, title="T", member_ids=[b])

        # b 의 unread 를 수동으로 5 로 세팅 (실제론 메시지 수신으로 증가)
        await redis_hot.hset(unread_key(b), room.chat_room_id, 5)

        chat_fanout_stub.reset_mock()
        final = await service.mark_read(
            me_id=b, me_session_id="WS_B", room_id=room.chat_room_id,
            up_to_server_seq=10,
        )
        assert final == 10

        # RDB 반영
        async with session_factory() as s:
            b_row = await s.get(ChatRoomMember, (room.chat_room_id, b))
            assert b_row.last_read_message_server_seq == 10
            assert b_row.last_read_at is not None

        # Redis unread 0
        raw = await redis_hot.hget(unread_key(b), room.chat_room_id)
        assert raw == "0"

        # fan-out: read_ack 발신 세션 직송
        chat_fanout_stub.fan_out_to_session.assert_awaited_once()
        sess_call = chat_fanout_stub.fan_out_to_session.call_args
        assert sess_call.args[0] == "WS_B"
        assert sess_call.args[1] == {
            "type": "read_ack", "room_id": room.chat_room_id, "up_to_server_seq": 10,
        }

        # fan-out: 방 전체에 read 이벤트 (sender_session_id 로 자기 에코 차단)
        chat_fanout_stub.fan_out_to_room.assert_awaited_once()
        room_call = chat_fanout_stub.fan_out_to_room.call_args
        assert room_call.args[0] == room.chat_room_id
        assert room_call.args[1] == {
            "type": "read",
            "user_id": b,
            "sender_session_id": "WS_B",
            "up_to_server_seq": 10,
        }


    async def test_greatest_prevents_regress(
        self, uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
        session_factory, patch_external_clients,
    ):
        """이미 높은 seq 가 기록된 뒤 과거 seq 로 호출 → 기존 값 유지, 반환도 기존 값."""
        a, b, _ = await seed_users(3)
        await seed_friendship(a, b)

        service = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await service.create_group_room(me_id=a, title="T", member_ids=[b])

        first = await service.mark_read(
            me_id=b, me_session_id="WS_B", room_id=room.chat_room_id,
            up_to_server_seq=20,
        )
        assert first == 20

        # 과거 seq=5 로 재호출 — regress 되지 않고 20 유지
        second = await service.mark_read(
            me_id=b, me_session_id="WS_B", room_id=room.chat_room_id,
            up_to_server_seq=5,
        )
        assert second == 20

        async with session_factory() as s:
            b_row = await s.get(ChatRoomMember, (room.chat_room_id, b))
            assert b_row.last_read_message_server_seq == 20


    async def test_room_not_found_raises(
        self, uow, chat_fanout_stub, message_service, patch_external_clients,
    ):
        service = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        with pytest.raises(ChatRoomNotFoundError):
            await service.mark_read(
                me_id="U_ghost", me_session_id="WS_x", room_id="CR_none",
                up_to_server_seq=1,
            )


    async def test_left_member_cannot_mark_read(
        self, uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
        session_factory, patch_external_clients,
    ):
        a, b, _ = await seed_users(3)
        await seed_friendship(a, b)

        service = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await service.create_group_room(me_id=a, title="T", member_ids=[b])
        await service.leave_room(me_id=b, room_id=room.chat_room_id)

        with pytest.raises(PermissionError):
            await service.mark_read(
                me_id=b, me_session_id="WS_B", room_id=room.chat_room_id,
                up_to_server_seq=5,
            )


    async def test_count_readers_up_to_excludes_sender_and_left(
        self, uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
        session_factory, patch_external_clients,
    ):
        """카톡 숫자 뱃지 계산용 집계 — 탈퇴자/발신자 본인 제외, seq 이상 읽은 멤버만."""
        from app.domain.chat.repository.chat_member import ChatRoomMemberRepository

        a, b, c = await seed_users(3)
        await seed_friendship(a, b)
        await seed_friendship(a, c)

        service = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await service.create_group_room(me_id=a, title="T", member_ids=[b, c])

        # b 만 seq=10 까지 읽음
        await service.mark_read(
            me_id=b, me_session_id="WS_B", room_id=room.chat_room_id,
            up_to_server_seq=10,
        )

        async with session_factory() as s:
            repo = ChatRoomMemberRepository(s)
            # a 가 방금 보낸 seq=10 를 b 가 읽었는지 집계 (c 는 아직, a 는 exclude)
            count = await repo.count_readers_up_to(room.chat_room_id, 10, a)
            assert count == 1  # b 만

            # 더 높은 seq 는 아무도 못 읽음
            count2 = await repo.count_readers_up_to(room.chat_room_id, 100, a)
            assert count2 == 0
