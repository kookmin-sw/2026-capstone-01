from unittest.mock import AsyncMock, MagicMock


class FakeAsyncContextManager:
    """`async with` 프로토콜만 지원하는 단순한 가짜 컨텍스트매니저."""

    async def __aenter__(self):
        return self


    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeUnitOfWork:
    """`transactional` 데코레이터가 쓰는 `async with self.uow as session:` 를 만족시킨다."""

    def __init__(self, session):
        self._session = session


    async def __aenter__(self):
        return self._session


    async def __aexit__(self, exc_type, exc, tb):
        return False


def make_mock_session() -> MagicMock:
    """서비스 내부에서 `self._session` 으로 접근하는 메서드만 Mock 제공."""
    session = MagicMock(name="session")
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.begin_nested = MagicMock(return_value=FakeAsyncContextManager())
    return session


class FriendshipRepositoryMockFactory:
    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.save.return_value = None
        mock.find_by_id.return_value = None
        mock.find_between.return_value = None
        mock.find_friendships_with.return_value = {}
        mock.find_friends.return_value = []
        mock.find_received_requests.return_value = []
        mock.find_sent_requests.return_value = []
        mock.update.return_value = None
        mock.delete.return_value = None
        return mock


class UserBlockRepositoryMockFactory:
    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.save.return_value = None
        mock.find_by_id.return_value = None
        mock.find_by_pair.return_value = None
        mock.find_blocks_between.return_value = []
        mock.has_blocker_blocked.return_value = False
        mock.find_blocks_by_user.return_value = []
        mock.delete.return_value = None
        return mock


class UserRepositoryMockFactory:
    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.find_by_id.return_value = None
        mock.find_by_id_with_profile.return_value = None
        return mock
