from unittest.mock import AsyncMock, MagicMock


class FakeAsyncContextManager:
    """`async with` 프로토콜만 지원하는 단순한 가짜 컨텍스트매니저.

    SAVEPOINT (`session.begin_nested()`) 자리에 끼워넣는 용도.
    """

    async def __aenter__(self):
        return self


    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeUnitOfWork:
    """`@transactional` 이 쓰는 `async with self.uow as session:` 를 만족."""

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


class TourPlanRepositoryMockFactory:
    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.save.return_value = None
        mock.find_by_id.return_value = None
        mock.find_by_id_with_items.return_value = None
        mock.find_all_by_user_id.return_value = []
        mock.update.return_value = None
        mock.delete.return_value = None
        return mock


class TourPlanItemRepositoryMockFactory:
    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.save.return_value = None
        mock.save_all.return_value = []
        mock.find_by_id.return_value = None
        mock.find_by_plan_id.return_value = []
        mock.update.return_value = None
        mock.delete.return_value = None
        mock.delete_by_plan_and_day.return_value = None
        return mock


class PlaceRepositoryMockFactory:
    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.find_by_place_id.return_value = None
        mock.find_by_place_ids.return_value = []
        return mock
