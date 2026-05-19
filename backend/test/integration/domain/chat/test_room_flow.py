"""RoomService 통합 테스트 — 실제 RDB + Repository 경유.

Redis / Fanout 는 Mock 으로 주입 (§통합 테스트 범위 — Phase 1 은 RDB 중심).
"""
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import select
import pytest

from app.domain.friend.model.user_block import UserBlock
from app.domain.chat.service.room import RoomService
from app.domain.chat.model.chat_room_member import ChatRoomMember
from app.domain.chat.model.chat_room import ChatRoom, ChatRoomType


pytestmark = pytest.mark.integration


# ──────────────────────────────────────────────────────────────────
# 공통 fixture
# ──────────────────────────────────────────────────────────────────

@pytest.fixture
def fanout_stub() -> MagicMock:
    """Redis / fan-out 경로는 통합 테스트 범위 밖 — Mock 으로 격리.

    `FanoutService` 의 모든 비동기 메서드를 AsyncMock 으로 셋업해야 `await` 가 안전.
    subscribe/unsubscribe 는 RoomService 의 방 멤버 변경 경로 (`create_*_room` /
    `invite_users` / `leave_room` / `kick_user`) 전부에서 await 된다.
    """
    mock = MagicMock(name="fanout")
    mock.fan_out_to_user = AsyncMock()
    mock.fan_out_to_session = AsyncMock()
    mock.fan_out_to_room = AsyncMock()
    mock.subscribe_user_to_room = AsyncMock()
    mock.unsubscribe_user_from_room = AsyncMock()
    return mock


@pytest.fixture
def message_service_stub() -> AsyncMock:
    """1:1 방은 시스템 메시지를 발행하지 않으므로 실제 호출되지 않는다 — 생성자 채움용 stub."""
    mock = MagicMock(name="chat-service")
    mock.send_system_message = AsyncMock()
    return mock


@pytest.fixture(autouse=True)
def stub_redis(monkeypatch):
    """Redis 연결 없이 테스트 — SADD/EXPIRE no-op."""
    pipe = MagicMock()
    pipe.sadd = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock()

    redis = MagicMock()
    redis.pipeline = MagicMock(return_value=pipe)

    async def _get_client():
        return redis

    monkeypatch.setattr(
        "app.domain.chat.service.room.get_redis_client",
        _get_client,
    )


# ──────────────────────────────────────────────────────────────────
# 1:1 방 생성
# ──────────────────────────────────────────────────────────────────

class TestCreateDirectRoomFlow:
    async def test_creates_room_and_two_members(
        self, uow, seed_users, session_factory, fanout_stub, message_service_stub,
    ):
        a, b, _ = await seed_users(3)
        service = RoomService(uow=uow, fanout_service=fanout_stub, message_service=message_service_stub)

        result = await service.create_direct_room(me_id=a, peer_user_id=b)

        assert result.type == ChatRoomType.DIRECT
        assert result.peer.user_id == b

        async with session_factory() as s:
            rooms = (await s.execute(select(ChatRoom))).scalars().all()
            members = (await s.execute(select(ChatRoomMember))).scalars().all()
            assert len(rooms) == 1
            assert len(members) == 2

        # fan_out_to_user 가 양쪽에 1회씩 호출 (본인 포함)
        assert fanout_stub.fan_out_to_user.await_count == 2


    async def test_canonical_order_persisted(
        self, uow, seed_users, session_factory, fanout_stub, message_service_stub,
    ):
        """me, peer 순서에 상관없이 항상 direct_user_a_id < direct_user_b_id."""
        a, b, _ = await seed_users(3)
        low, high = sorted([a, b])
        service = RoomService(uow=uow, fanout_service=fanout_stub, message_service=message_service_stub)

        await service.create_direct_room(me_id=high, peer_user_id=low)

        async with session_factory() as s:
            row = (await s.execute(select(ChatRoom))).scalar_one()
            assert row.direct_user_a_id == low
            assert row.direct_user_b_id == high
            assert row.direct_user_a_id < row.direct_user_b_id


    async def test_idempotent_returns_same_room_id(
        self, uow, seed_users, session_factory, fanout_stub, message_service_stub,
    ):
        a, b, _ = await seed_users(3)
        service = RoomService(uow=uow, fanout_service=fanout_stub, message_service=message_service_stub)

        first = await service.create_direct_room(me_id=a, peer_user_id=b)
        second = await service.create_direct_room(me_id=a, peer_user_id=b)

        assert first.chat_room_id == second.chat_room_id

        async with session_factory() as s:
            rooms = (await s.execute(select(ChatRoom))).scalars().all()
            members = (await s.execute(select(ChatRoomMember))).scalars().all()
            assert len(rooms) == 1        # 중복 생성 없음
            assert len(members) == 2

        # 두 번째 호출에선 fan-out 스킵 (기존 방 반환)
        assert fanout_stub.fan_out_to_user.await_count == 2  # 첫 호출만


    async def test_reverse_direction_returns_same_room(
        self, uow, seed_users, fanout_stub, message_service_stub, session_factory,
    ):
        """A→B 방 생성 후 B→A 로 호출해도 같은 방 반환 (canonical 덕)."""
        a, b, _ = await seed_users(3)
        service = RoomService(uow=uow, fanout_service=fanout_stub, message_service=message_service_stub)

        first = await service.create_direct_room(me_id=a, peer_user_id=b)
        second = await service.create_direct_room(me_id=b, peer_user_id=a)

        assert first.chat_room_id == second.chat_room_id

        async with session_factory() as s:
            rooms = (await s.execute(select(ChatRoom))).scalars().all()
            assert len(rooms) == 1


    async def test_self_raises(self, uow, seed_users, fanout_stub, message_service_stub):
        (a,) = await seed_users(1)
        service = RoomService(uow=uow, fanout_service=fanout_stub, message_service=message_service_stub)

        with pytest.raises(ValueError, match="자기 자신"):
            await service.create_direct_room(me_id=a, peer_user_id=a)


    async def test_unknown_peer_raises(self, uow, seed_users, fanout_stub, message_service_stub):
        (a,) = await seed_users(1)
        service = RoomService(uow=uow, fanout_service=fanout_stub, message_service=message_service_stub)

        with pytest.raises(ValueError, match="존재하지 않는"):
            await service.create_direct_room(me_id=a, peer_user_id="USER_ghost")


    async def test_blocked_raises(self, uow, seed_users, session_factory, fanout_stub, message_service_stub):
        a, b, _ = await seed_users(3)

        async with session_factory() as s:
            s.add(UserBlock(blocker_id=a, blocked_id=b))
            await s.commit()

        service = RoomService(uow=uow, fanout_service=fanout_stub, message_service=message_service_stub)

        with pytest.raises(ValueError, match="차단한"):
            await service.create_direct_room(me_id=a, peer_user_id=b)


# ──────────────────────────────────────────────────────────────────
# list_user_room_ids
# ──────────────────────────────────────────────────────────────────

class TestListUserRoomIdsFlow:
    async def test_returns_only_active_rooms(
        self, uow, seed_users, session_factory, fanout_stub, message_service_stub,
    ):
        a, b, c = await seed_users(3)
        service = RoomService(uow=uow, fanout_service=fanout_stub, message_service=message_service_stub)

        # a-b 방, a-c 방 두 개 생성 후 a 가 두 번째만 나감
        r1 = await service.create_direct_room(me_id=a, peer_user_id=b)
        r2 = await service.create_direct_room(me_id=a, peer_user_id=c)

        async with session_factory() as s:
            await s.execute(
                ChatRoomMember.__table__.update()
                .where(ChatRoomMember.chat_room_id == r2.chat_room_id)
                .where(ChatRoomMember.user_id == a)
                .values(is_left=True)
            )
            await s.commit()

        ids = await service.list_user_room_ids(a)
        assert ids == [r1.chat_room_id]
