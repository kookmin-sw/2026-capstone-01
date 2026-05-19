"""PlaceService 단위 테스트용 Mock 팩토리.

의존성:
    - PlaceRepository (Mongo, motor) — `find_nearby` / `search_nearby` / `find_by_place_id`
    - FavoritePlaceRepository (RDB) — `_get_favorited_set` 의 `find_favorited_place_ids` 만 사용

tour_plan_service 의 mock_factory 패턴과 일관.
"""
from unittest.mock import AsyncMock, MagicMock


class FakeUnitOfWork:
    """`@transactional` 의 `async with self.uow as session:` 패턴 충족."""

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


class PlaceRepositoryMockFactory:
    """Mongo `PlaceRepository` mock — service 가 사용하는 메서드만."""

    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.find_nearby.return_value = []
        mock.search_nearby.return_value = []
        mock.find_by_place_id.return_value = None
        mock.find_by_place_ids.return_value = []
        return mock


class FavoritePlaceRepositoryMockFactory:
    """RDB `FavoritePlaceRepository` mock."""

    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.find_favorited_place_ids.return_value = set()
        mock.find_by_user_and_place.return_value = None
        mock.find_all_by_user.return_value = []
        mock.save.side_effect = lambda fav: fav
        mock.delete_by_user_and_place.return_value = None
        return mock
