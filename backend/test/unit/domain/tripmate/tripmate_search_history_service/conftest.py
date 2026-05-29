"""TripmateSearchHistoryService 단위 테스트 fixtures.

repo (Mongo beanie) 단일 의존 — service 인스턴스화 후 `service.search_repo` 직접 치환.
tour_search_history_service 와 동일 시그니처지만 별도 fixture 로 도메인 격리 유지.
"""
from unittest.mock import AsyncMock
import pytest

from app.domain.tripmate.service.tripmate_search_history import (
    TripmateSearchHistoryService,
)


@pytest.fixture
def search_repo_mock():
    mock = AsyncMock()
    mock.save.return_value = None
    mock.find_by_user_id.return_value = []
    mock.delete_one.return_value = None
    mock.delete_all_by_user_id.return_value = None
    return mock


@pytest.fixture
def service(search_repo_mock):
    service = TripmateSearchHistoryService()
    service.search_repo = search_repo_mock
    return service
