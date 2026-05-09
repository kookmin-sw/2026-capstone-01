"""RoomService 단위 테스트용 Mock 팩토리."""
from unittest.mock import AsyncMock, MagicMock


class FakeAsyncContextManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


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
    mock = AsyncMock()
    mock.save.return_value = None
    mock.find_by_id.return_value = None
    mock.find_direct_by_pair.return_value = None
    mock.find_rooms_of_user.return_value = []
    mock.update_last_message.return_value = None
    return mock


def make_chat_member_repo_mock() -> AsyncMock:
    mock = AsyncMock()
    mock.save.return_value = None
    mock.save_all.return_value = None
    mock.find.return_value = None
    mock.update.return_value = None
    mock.find_active_member_ids.return_value = []
    mock.is_active_member.return_value = False
    mock.find_user_room_ids.return_value = []
    mock.mark_read.return_value = None
    mock.count_readers_up_to.return_value = 0
    return mock


def make_user_block_repo_mock() -> AsyncMock:
    mock = AsyncMock()
    mock.find_blocks_between.return_value = []
    return mock


def make_user_repo_mock() -> AsyncMock:
    mock = AsyncMock()
    mock.find_by_id_with_profile.return_value = None
    return mock


def make_friendship_repo_mock() -> AsyncMock:
    """Phase 2 그룹 초대 친구 검증용. 기본값은 "전원 친구" 로 세팅 — 테스트에서
    오버라이드해 비친구 케이스 커버."""
    mock = AsyncMock()
    mock.find_accepted_friend_ids_with.return_value = set()
    return mock


def make_chat_message_repo_mock() -> AsyncMock:
    """Phase 2 invite 시 current_seq fallback 용. 기본 0 (빈 방)."""
    mock = AsyncMock()
    mock.get_max_server_seq.return_value = 0
    return mock


def make_fanout_mock() -> MagicMock:
    fanout = MagicMock(name="fanout")
    fanout.fan_out_to_session = AsyncMock()
    fanout.fan_out_to_user = AsyncMock()
    fanout.fan_out_to_room = AsyncMock()
    # Phase 4 (node_channel) 진입 후 subscribe/unsubscribe 도 async — RoomService 가
    # await 로 호출하므로 AsyncMock 으로 매칭.
    fanout.subscribe_user_to_room = AsyncMock()
    fanout.unsubscribe_user_from_room = AsyncMock()
    return fanout


def _make_pipeline(parent) -> MagicMock:
    p = MagicMock(name="pipeline")
    # 체이닝 가능한 명령들
    for cmd in ("sadd", "srem", "expire", "hset", "hdel"):
        setattr(p, cmd, MagicMock(return_value=p))
    p.execute = AsyncMock()
    parent._pipes.append(p)
    return p


def make_redis_mock() -> MagicMock:
    redis = MagicMock(name="redis")
    redis._pipes: list = []

    redis.pipeline = MagicMock(side_effect=lambda *_a, **_kw: _make_pipeline(redis))

    # 직접 호출 메서드들 (Phase 2 invite 에서 `redis.get(room_seq_key)` 등)
    redis.get = AsyncMock(return_value=None)
    redis.srem = AsyncMock(return_value=1)
    redis.hdel = AsyncMock(return_value=1)
    redis.sadd = AsyncMock(return_value=0)
    redis.expire = AsyncMock(return_value=True)
    redis.hset = AsyncMock(return_value=0)

    return redis
