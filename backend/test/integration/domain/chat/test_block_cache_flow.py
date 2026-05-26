"""차단 캐시 훅 end-to-end 통합 (PHASE_2 #6 + #7).

friend 도메인의 `block_user` / `unblock_user` 가 chat 의 `BlockCacheService` 를 통해
Redis `room:blocks:{R}` 캐시를 **즉시** 무효화하고, 다음 `send_message` 가 새 상태를
반영하는지 검증. "캐시 TTL 대기 없음" 이 PHASE_2 #6 통합 체크리스트의 핵심.
"""
import pytest_asyncio
import pytest

from app.domain.friend.service.user_block import UserBlockService
from app.domain.chat.service.room import RoomService
from app.domain.chat.service.block_cache import BlockCacheService
from app.domain.chat.model.chat_message import MessageType
from app.core.chat.redis_key import room_blocks_key


pytestmark = pytest.mark.integration


class TestBlockCacheInvalidationFlow:
    async def test_block_invalidates_cache_and_next_send_is_rejected(
        self, uow, seed_users, chat_fanout_stub, message_service, redis_hot,
        patch_external_clients,
    ):
        """정상 대화 → block 후 즉시 송신 거절 (캐시 TTL 대기 없음)."""
        a, b, _ = await seed_users(3)

        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await room_svc.create_direct_room(me_id=a, peer_user_id=b)
        room_id = room.chat_room_id

        # 1) 차단 전: 정상 송신 → room:blocks 캐시에 __none__ sentinel 적재됨
        await message_service.send_message(
            sender_user_id=a, sender_session_id="WS_A", room_id=room_id,
            client_msg_id="cm-1", msg_type=MessageType.TEXT, content="hi",
        )
        assert await redis_hot.sismember(room_blocks_key(room_id), "__none__")

        # 2) a 가 b 를 차단 — UserBlockService 가 BlockCacheService 훅 호출
        block_cache = BlockCacheService(uow=uow)
        block_service = UserBlockService(uow=uow, block_cache_service=block_cache)
        await block_service.block_user(user_id=a, target_user_id=b)

        # 3) 캐시가 즉시 DEL — __none__ sentinel 사라짐
        assert not await redis_hot.exists(room_blocks_key(room_id))

        # 4) 다음 송신 → miss-through 로 user_block 재조회 → 차단 감지 → 거절
        with pytest.raises(PermissionError, match="차단"):
            await message_service.send_message(
                sender_user_id=a, sender_session_id="WS_A", room_id=room_id,
                client_msg_id="cm-2", msg_type=MessageType.TEXT, content="blocked",
            )


    async def test_unblock_allows_immediate_next_send(
        self, uow, seed_users, chat_fanout_stub, message_service, redis_hot,
        patch_external_clients,
    ):
        """차단 → 해제 즉시 송신 가능 (TTL 대기 없음)."""
        a, b, _ = await seed_users(3)

        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await room_svc.create_direct_room(me_id=a, peer_user_id=b)
        room_id = room.chat_room_id

        block_cache = BlockCacheService(uow=uow)
        block_service = UserBlockService(uow=uow, block_cache_service=block_cache)

        # 차단 상태에서 송신 거절 확인
        await block_service.block_user(user_id=a, target_user_id=b)
        with pytest.raises(PermissionError):
            await message_service.send_message(
                sender_user_id=a, sender_session_id="WS_A", room_id=room_id,
                client_msg_id="cm-a1", msg_type=MessageType.TEXT, content="x",
            )

        # 해제 — BlockCacheService.invalidate 가 먼저 돌아 캐시가 즉시 stale 제거
        await block_service.unblock_user(user_id=a, target_user_id=b)
        assert not await redis_hot.exists(room_blocks_key(room_id))

        # 즉시 송신 가능
        ack = await message_service.send_message(
            sender_user_id=a, sender_session_id="WS_A", room_id=room_id,
            client_msg_id="cm-a2", msg_type=MessageType.TEXT, content="restored",
        )
        assert ack.server_seq > 0
        # miss-through 가 __none__ sentinel 로 캐시를 재구성
        assert await redis_hot.sismember(room_blocks_key(room_id), "__none__")


    async def test_peer_blocking_sender_also_rejects(
        self, uow, seed_users, chat_fanout_stub, message_service, redis_hot,
        patch_external_clients,
    ):
        """상대가 나를 차단했어도 내 송신은 거절 (양방향 체크)."""
        a, b, _ = await seed_users(3)
        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await room_svc.create_direct_room(me_id=a, peer_user_id=b)

        # b 가 a 를 차단 — 그런데 room 은 이미 생성된 상태 (기존 채팅방 유지 정책)
        block_cache = BlockCacheService(uow=uow)
        block_service = UserBlockService(uow=uow, block_cache_service=block_cache)
        await block_service.block_user(user_id=b, target_user_id=a)

        with pytest.raises(PermissionError, match="차단"):
            await message_service.send_message(
                sender_user_id=a, sender_session_id="WS_A", room_id=room.chat_room_id,
                client_msg_id="cm-peer-1", msg_type=MessageType.TEXT, content="nope",
            )


    async def test_group_room_unaffected_by_block(
        self, uow, seed_users, chat_fanout_stub, message_service,
        patch_external_clients, session_factory,
    ):
        """그룹 방은 차단 관계와 무관 — 같은 방에 있으면 메시지는 계속 전달."""
        from app.domain.friend.model.friendship import Friendship, FriendshipStatus

        a, b, _ = await seed_users(3)
        async with session_factory() as s:
            s.add(Friendship(
                requester_id=a, addressee_id=b, status=FriendshipStatus.ACCEPTED,
            ))
            await s.commit()

        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await room_svc.create_group_room(me_id=a, title="T", member_ids=[b])

        # 이미 그룹 방에 있는 상태에서 a 가 b 를 차단해도 그룹 송신은 유지
        # (차단은 friendship 을 삭제하지만 그룹 방 멤버십은 그대로)
        block_cache = BlockCacheService(uow=uow)
        block_service = UserBlockService(uow=uow, block_cache_service=block_cache)
        await block_service.block_user(user_id=a, target_user_id=b)

        ack = await message_service.send_message(
            sender_user_id=a, sender_session_id="WS_A", room_id=room.chat_room_id,
            client_msg_id="cm-g-1", msg_type=MessageType.TEXT, content="group msg",
        )
        assert ack.server_seq > 0
