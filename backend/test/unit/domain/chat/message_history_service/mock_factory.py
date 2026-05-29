"""MessageHistoryService 단위 테스트용 Mock 팩토리.

공통 FakeUnitOfWork / FakeAsyncContextManager 는 다른 chat 단위 모듈과 동일한
규약을 사용. 각 mock 은 기본값을 "빈 결과 / 미존재" 로 세팅 — 테스트에서 override.
"""
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
    return session


def make_chat_room_repo_mock() -> AsyncMock:
    mock = AsyncMock()
    mock.find_rooms_of_user.return_value = []
    return mock


def make_chat_member_repo_mock() -> AsyncMock:
    mock = AsyncMock()
    mock.is_active_member.return_value = False
    mock.find_active_member_users.return_value = []
    mock.find_active_member_ids.return_value = []
    return mock


def make_friendship_repo_mock() -> AsyncMock:
    mock = AsyncMock()
    mock.find_accepted_friend_ids.return_value = set()
    return mock


def make_message_repo_mock() -> AsyncMock:
    mock = AsyncMock()
    mock.find_before.return_value = []
    mock.find_after.return_value = []
    mock.find_by_ids.return_value = {}
    return mock


def make_user_repo_mock() -> AsyncMock:
    mock = AsyncMock()
    mock.find_by_id_with_profile.return_value = None
    mock.find_by_ids_with_profile.return_value = {}
    return mock


def make_redis_mock() -> MagicMock:
    redis = MagicMock(name="redis")
    redis.hgetall = AsyncMock(return_value={})
    redis.hget = AsyncMock(return_value=None)
    return redis
