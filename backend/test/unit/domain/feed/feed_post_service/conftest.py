from unittest.mock import AsyncMock
from test.unit.domain.feed.mock_factory import (
    FakeUnitOfWork,
    make_feed_post_repo_mock,
    make_friendship_repo_mock,
    make_mock_session,
    make_object_storage_mock,
    make_user_block_repo_mock,
)
import pytest

from app.domain.feed.service.feed_post import FeedPostService


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture
def repo_mock():
    return make_feed_post_repo_mock()


@pytest.fixture
def storage_mock():
    return make_object_storage_mock()


@pytest.fixture
def friendship_repo_mock():
    return make_friendship_repo_mock()


@pytest.fixture
def block_repo_mock():
    return make_user_block_repo_mock()


@pytest.fixture
def inbox_service_mock():
    """인박스 cascade 진입점 mock — `delete_post` 후 cascade_post_deleted 호출 검증용."""
    mock = AsyncMock()
    mock.cascade_post_deleted.return_value = 0
    return mock


@pytest.fixture
def service(
    monkeypatch, mock_session,
    repo_mock, storage_mock, friendship_repo_mock, block_repo_mock,
    inbox_service_mock,
):
    """FeedPostRepository / ObjectStorage / Friendship / UserBlock 모두 mock 주입.

    Friendship / UserBlock repo 의 인스턴스화는 `service/access.py` 의 free function
    안에서 일어나므로 그쪽 경로를 monkeypatch (feed_post.py 가 아닌 access.py).
    FeedPostRepository 는 access 와 service 양쪽 모두에서 인스턴스화 → 두 경로 다 패치.
    """
    monkeypatch.setattr(
        "app.domain.feed.service.feed_post.FeedPostRepository",
        lambda session: repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.feed.service.access.FeedPostRepository",
        lambda session: repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.feed.service.access.FriendshipRepository",
        lambda session: friendship_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.feed.service.access.UserBlockRepository",
        lambda session: block_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.feed.service.feed_post.get_object_storage",
        lambda: storage_mock,
    )

    uow = FakeUnitOfWork(mock_session)
    return FeedPostService(uow=uow, inbox_service=inbox_service_mock)
