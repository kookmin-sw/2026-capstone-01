"""TripmateSearchHistoryService — 검색어 저장/조회/삭제 단위 테스트.

repo thin wrapper — repo 호출 인자 정확성 검증. tour_search_history_service 와 동일
시그니처지만 도메인 별도 (향후 진화 여지).
"""
from types import SimpleNamespace
import pytest


@pytest.mark.unit
class TestSaveSearch:
    """Tests for TripmateSearchHistoryService.save_search."""

    async def test_calls_repo_save_with_user_and_keyword(
        self, service, search_repo_mock,
    ):
        await service.save_search(user_id="USER_a", search_name="제주")

        search_repo_mock.save.assert_awaited_once_with(
            user_id="USER_a", search_name="제주",
        )


@pytest.mark.unit
class TestGetSearchHistories:
    """Tests for TripmateSearchHistoryService.get_search_histories."""

    async def test_returns_repo_result(self, service, search_repo_mock):
        search_repo_mock.find_by_user_id.return_value = [
            SimpleNamespace(search_name="제주"),
        ]

        result = await service.get_search_histories(user_id="USER_a")

        assert len(result) == 1
        search_repo_mock.find_by_user_id.assert_awaited_once_with("USER_a")


@pytest.mark.unit
class TestDeleteSearch:
    """Tests for TripmateSearchHistoryService.delete_search."""

    async def test_calls_repo_delete_one(self, service, search_repo_mock):
        await service.delete_search(user_id="USER_a", search_name="제주")

        search_repo_mock.delete_one.assert_awaited_once_with(
            user_id="USER_a", search_name="제주",
        )


@pytest.mark.unit
class TestDeleteAllSearches:
    """Tests for TripmateSearchHistoryService.delete_all_searches."""

    async def test_calls_repo_delete_all(self, service, search_repo_mock):
        await service.delete_all_searches(user_id="USER_a")

        search_repo_mock.delete_all_by_user_id.assert_awaited_once_with("USER_a")
