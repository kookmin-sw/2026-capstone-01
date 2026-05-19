"""FriendSearchHistoryService 는 repository 위에 얇게 얹은 wrapper.

검증 대상은 "어떤 메서드가 어떤 인자로 repo 를 호출하느냐" 한 가지로 좁혀진다.
실제 MongoDB / Beanie 동작은 통합 테스트 / 운영 환경에서만 의미가 있다.
"""

from types import SimpleNamespace
import pytest
from datetime import datetime, timezone


@pytest.mark.unit
class TestSaveSearch:
    async def test_delegates_to_repo_with_keyword_args(self, service, repo_mock):
        await service.save_search(user_id="USER_a", search_name="조현상")

        repo_mock.save.assert_awaited_once_with(user_id="USER_a", search_name="조현상")


    async def test_returns_repo_result(self, service, repo_mock):
        saved = SimpleNamespace(
            user_id="USER_a",
            search_name="조현상",
            created_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
        )
        repo_mock.save.return_value = saved

        result = await service.save_search(user_id="USER_a", search_name="조현상")

        assert result is saved


@pytest.mark.unit
class TestGetSearchHistories:
    async def test_delegates_to_repo_with_user_id(self, service, repo_mock):
        repo_mock.find_by_user_id.return_value = []

        await service.get_search_histories("USER_a")

        repo_mock.find_by_user_id.assert_awaited_once_with("USER_a")


    async def test_returns_repo_result_unchanged(self, service, repo_mock):
        items = [
            SimpleNamespace(
                user_id="USER_a", search_name="조현상",
                created_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                user_id="USER_a", search_name="민수",
                created_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
            ),
        ]
        repo_mock.find_by_user_id.return_value = items

        result = await service.get_search_histories("USER_a")

        assert result is items


@pytest.mark.unit
class TestDeleteSearch:
    async def test_delegates_to_repo_with_keyword_args(self, service, repo_mock):
        await service.delete_search(user_id="USER_a", search_name="조현상")

        repo_mock.delete_one.assert_awaited_once_with(
            user_id="USER_a", search_name="조현상",
        )


@pytest.mark.unit
class TestDeleteAllSearches:
    async def test_delegates_to_repo_with_user_id(self, service, repo_mock):
        await service.delete_all_searches("USER_a")

        repo_mock.delete_all_by_user_id.assert_awaited_once_with("USER_a")
