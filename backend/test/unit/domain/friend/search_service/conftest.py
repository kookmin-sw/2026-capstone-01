from test.unit.domain.friend.search_service.model_factory import (
    FriendshipFactory,
    UserBlockFactory,
    UserFactory,
)
from test.unit.domain.friend.search_service.mock_factory import (
    FakeUnitOfWork,
    FriendSearchRepositoryMockFactory,
    FriendshipRepositoryMockFactory,
    make_mock_session,
)
import pytest

from app.domain.friend.service.search import FriendSearchService


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
def search_repo_mock():
    return FriendSearchRepositoryMockFactory.create()


@pytest.fixture
def friendship_repo_mock():
    return FriendshipRepositoryMockFactory.create()


@pytest.fixture
def service(
    monkeypatch,
    mock_session,
    search_repo_mock,
    friendship_repo_mock,
):
    """search/friendship 레포지토리가 Mock 으로 주입된 FriendSearchService."""
    monkeypatch.setattr(
        "app.domain.friend.service.search.FriendSearchRepository",
        lambda session: search_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.friend.service.search.FriendshipRepository",
        lambda session: friendship_repo_mock,
    )

    uow = FakeUnitOfWork(mock_session)
    return FriendSearchService(uow=uow)
