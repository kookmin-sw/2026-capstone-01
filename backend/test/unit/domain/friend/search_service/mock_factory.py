"""friendship_service 쪽 Mock 팩토리 재사용 + search 전용 mock 추가."""

from unittest.mock import AsyncMock
from test.unit.domain.friend.friendship_service.mock_factory import (
    FakeAsyncContextManager,
    FakeUnitOfWork,
    FriendshipRepositoryMockFactory,
    UserBlockRepositoryMockFactory,
    UserRepositoryMockFactory,
    make_mock_session,
)


class FriendSearchRepositoryMockFactory:
    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.search_active_users.return_value = []
        return mock


__all__ = [
    "FakeAsyncContextManager",
    "FakeUnitOfWork",
    "FriendshipRepositoryMockFactory",
    "UserBlockRepositoryMockFactory",
    "UserRepositoryMockFactory",
    "FriendSearchRepositoryMockFactory",
    "make_mock_session",
]
