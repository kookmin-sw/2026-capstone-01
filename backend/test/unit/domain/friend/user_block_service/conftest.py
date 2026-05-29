from test.unit.domain.friend.user_block_service.model_factory import (
    FriendshipFactory,
    UserBlockFactory,
    UserFactory,
)
from test.unit.domain.friend.user_block_service.mock_factory import (
    FakeUnitOfWork,
    FriendshipRepositoryMockFactory,
    UserBlockRepositoryMockFactory,
    UserRepositoryMockFactory,
    make_mock_session,
)
import pytest

from app.domain.friend.service.user_block import UserBlockService


@pytest.fixture(autouse=True)
def reset_factories():
    FriendshipFactory.reset_counter()
    UserBlockFactory.reset_counter()
    UserFactory.reset_counter()
    yield
    FriendshipFactory.reset_counter()
    UserBlockFactory.reset_counter()
    UserFactory.reset_counter()


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture
def friendship_repo_mock():
    return FriendshipRepositoryMockFactory.create()


@pytest.fixture
def block_repo_mock():
    return UserBlockRepositoryMockFactory.create()


@pytest.fixture
def user_repo_mock():
    return UserRepositoryMockFactory.create()


@pytest.fixture
def block_cache_service_stub():
    """PHASE_2 #6 — UserBlockService 가 주입받는 chat 도메인 훅. 단위는 mock."""
    from unittest.mock import AsyncMock, MagicMock
    mock = MagicMock(name="block_cache")
    mock.invalidate_block_cache = AsyncMock()
    return mock


@pytest.fixture
def service(
    monkeypatch,
    mock_session,
    friendship_repo_mock,
    block_repo_mock,
    user_repo_mock,
    block_cache_service_stub,
):
    monkeypatch.setattr(
        "app.domain.friend.service.user_block.UserBlockRepository",
        lambda session: block_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.friend.service.user_block.FriendshipRepository",
        lambda session: friendship_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.friend.service.user_block.UserRepository",
        lambda session: user_repo_mock,
    )

    uow = FakeUnitOfWork(mock_session)
    return UserBlockService(uow=uow, block_cache_service=block_cache_service_stub)
