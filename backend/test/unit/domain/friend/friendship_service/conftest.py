from test.unit.domain.friend.friendship_service.model_factory import (
    FriendshipFactory,
    UserBlockFactory,
    UserFactory,
)
from test.unit.domain.friend.friendship_service.mock_factory import (
    FakeUnitOfWork,
    FriendshipRepositoryMockFactory,
    UserBlockRepositoryMockFactory,
    UserRepositoryMockFactory,
    make_mock_session,
)
import pytest

from app.domain.friend.service.friendship import FriendshipService


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
def service(
    monkeypatch,
    mock_session,
    friendship_repo_mock,
    block_repo_mock,
    user_repo_mock,
):
    """모든 레포지토리 의존성이 Mock 으로 주입된 FriendshipService 를 반환."""
    monkeypatch.setattr(
        "app.domain.friend.service.friendship.FriendshipRepository",
        lambda session: friendship_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.friend.service.friendship.UserBlockRepository",
        lambda session: block_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.friend.service.friendship.UserRepository",
        lambda session: user_repo_mock,
    )

    uow = FakeUnitOfWork(mock_session)
    return FriendshipService(uow=uow)
