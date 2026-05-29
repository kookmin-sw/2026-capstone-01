"""MessageService 단위 테스트용 Mock 팩토리."""
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace


class FakeAsyncContextManager:
    async def __aenter__(self):
        return self


    async def __aexit__(self, exc_type, exc, tb):
        return False


class RaisingAsyncContextManager:
    """`async with` 블록을 즉시 실패시키는 헬퍼 — RDB UPDATE 실패 재현."""

    def __init__(self, exc: Exception):
        self._exc = exc


    async def __aenter__(self):
        return None


    async def __aexit__(self, exc_type, exc, tb):
        raise self._exc


class FakeUnitOfWork:
    def __init__(self, session):
        self._session = session


    async def __aenter__(self):
        return self._session


    async def __aexit__(self, exc_type, exc, tb):
        return False


def make_mock_session() -> MagicMock:
    session = MagicMock(name="session")
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.begin_nested = MagicMock(return_value=FakeAsyncContextManager())
    return session


def make_chat_room_repo_mock() -> AsyncMock:
    """기본 반환은 GROUP 방 — 기존 Phase 1 테스트의 `send_message` 가 차단 체크(4) 를
    skip 하도록. DIRECT 시나리오는 각 테스트에서 override.
    """
    from app.domain.chat.model.chat_room import ChatRoomType as _CRT
    mock = AsyncMock()
    mock.update_last_message.return_value = None
    mock.find_by_id.return_value = SimpleNamespace(
        chat_room_id="CR_1",
        type=_CRT.GROUP,
        creator_id=None,
        direct_user_a_id=None,
        direct_user_b_id=None,
    )
    return mock


def make_chat_member_repo_mock() -> AsyncMock:
    mock = AsyncMock()
    mock.find_active_member_ids.return_value = ["U_A", "U_B"]
    mock.is_active_member.return_value = True
    return mock


def make_message_repo_mock() -> AsyncMock:
    mock = AsyncMock()
    mock.insert.return_value = None
    mock.get_max_server_seq.return_value = 0
    mock.find_by_id.return_value = None
    mock.update_content.return_value = True
    mock.soft_delete.return_value = True
    return mock


def make_fanout_mock() -> MagicMock:
    fanout = MagicMock(name="fanout")
    fanout.fan_out_to_session = AsyncMock()
    fanout.fan_out_to_user = AsyncMock()
    fanout.fan_out_to_room = AsyncMock()
    return fanout


def make_fcm_mock() -> MagicMock:
    """FCM 발송은 fire-and-forget — push 가 호출되든 말든 본 비즈 테스트는 영향 없음."""
    fcm = MagicMock(name="fcm")
    fcm.send_chat_push = AsyncMock(return_value=0)
    fcm.register_token = AsyncMock()
    fcm.unregister_token = AsyncMock()
    return fcm


def _make_trackable_pipe() -> MagicMock:
    pipe = MagicMock(name="pipeline")
    for name in ("sadd", "expire", "hincrby", "hset", "zadd", "set", "delete", "zrem"):
        setattr(pipe, name, MagicMock(return_value=pipe))
    pipe.execute = AsyncMock()
    return pipe


def make_redis_mock() -> MagicMock:
    """hot Redis — sismember / smembers / sadd / pipeline 등."""
    redis = MagicMock(name="redis-hot")
    redis._pipes: list = []

    redis.sismember = AsyncMock(return_value=True)
    redis.smembers = AsyncMock(return_value={"U_A", "U_B"})
    redis.sadd = AsyncMock(return_value=1)

    def _new_pipe(*_a, **_kw):
        p = _make_trackable_pipe()
        redis._pipes.append(p)
        return p

    redis.pipeline = MagicMock(side_effect=_new_pipe)
    return redis


def make_dedupe_redis_mock(first_time: bool = True) -> MagicMock:
    """dedupe Redis — SET NX 반환값에 따라 dedupe 시나리오 제어."""
    redis = MagicMock(name="redis-dedupe")
    redis.set = AsyncMock(return_value=first_time)  # SET NX 결과
    redis.delete = AsyncMock(return_value=1)
    return redis


def make_lua_mock(
    *,
    incr_fast_return: int = 100,
    recover_and_incr_return: int = 1001,
    force_jump_return: int = 2000,
    incr_with_ttl_return: int = 1,
) -> SimpleNamespace:
    """lua_scripts 대체용. 호출 횟수 / 인자는 AsyncMock 으로 추적."""
    return SimpleNamespace(
        incr_fast=AsyncMock(return_value=incr_fast_return),
        recover_and_incr=AsyncMock(return_value=recover_and_incr_return),
        force_jump=AsyncMock(return_value=force_jump_return),
        incr_with_ttl=AsyncMock(return_value=incr_with_ttl_return),
    )
