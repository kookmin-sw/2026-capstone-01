from unittest.mock import AsyncMock
import pytest

from app.domain.friend.service.search_history import FriendSearchHistoryService


@pytest.fixture
def repo_mock() -> AsyncMock:
    """FriendSearchHistoryRepository 의 모든 호출을 AsyncMock 으로 대체."""
    return AsyncMock()


@pytest.fixture
def service(repo_mock):
    """FriendSearchHistoryService — repo 만 mock 으로 교체.

    서비스가 ``__init__`` 에서 repo 를 직접 인스턴스화하므로,
    인스턴스 생성 후 ``search_repo`` 속성을 mock 으로 바꿔치기한다.
    """
    svc = FriendSearchHistoryService()
    svc.search_repo = repo_mock
    return svc
