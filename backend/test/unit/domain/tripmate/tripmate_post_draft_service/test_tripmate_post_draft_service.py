"""TripmatePostDraftService — 임시저장 upsert/조회/삭제 단위 테스트.

검증 대상:
    - `save_draft`: 입력 field 매핑 + upsert 호출
    - `save_draft`: image_urls=None 시 빈 리스트로 정규화
    - `get_draft`: 정상 / None
    - `delete_draft`: repo 호출
"""
import pytest
from datetime import date


# ──────────────────────────────────────────────────────────────────
# save_draft
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSaveDraft:
    """Tests for TripmatePostDraftService.save_draft."""

    async def test_upserts_draft_with_input_fields(self, service, draft_repo_mock):
        await service.save_draft(
            user_id="USER_a",
            title="여행",
            content="content",
            preferred_age_min=20,
            preferred_age_max=30,
            preferred_gender="any",
            region="제주",
            travel_start_date=date(2026, 6, 1),
            travel_end_date=date(2026, 6, 5),
            companion_type="friend",
            image_urls=["https://img/1"],
        )

        draft_repo_mock.upsert.assert_awaited_once()
        saved = draft_repo_mock.upsert.await_args.args[0]
        assert saved.user_id == "USER_a"
        assert saved.title == "여행"
        assert saved.image_urls == ["https://img/1"]


    async def test_normalizes_none_image_urls_to_empty_list(
        self, service, draft_repo_mock,
    ):
        """image_urls=None → [] 로 정규화 (DB 에 null 안 들어감)."""
        await service.save_draft(user_id="USER_a", image_urls=None)

        saved = draft_repo_mock.upsert.await_args.args[0]
        assert saved.image_urls == []


# ──────────────────────────────────────────────────────────────────
# get_draft / delete_draft
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetDraft:
    """Tests for TripmatePostDraftService.get_draft."""

    async def test_returns_draft_when_exists(self, service, draft_repo_mock):
        from types import SimpleNamespace
        draft_repo_mock.find_by_user_id.return_value = SimpleNamespace(user_id="USER_a")

        result = await service.get_draft(user_id="USER_a")

        assert result is not None
        assert result.user_id == "USER_a"


    async def test_returns_none_when_no_draft(self, service, draft_repo_mock):
        draft_repo_mock.find_by_user_id.return_value = None

        result = await service.get_draft(user_id="USER_a")

        assert result is None


@pytest.mark.unit
class TestDeleteDraft:
    """Tests for TripmatePostDraftService.delete_draft."""

    async def test_calls_repo_delete(self, service, draft_repo_mock):
        await service.delete_draft(user_id="USER_a")

        draft_repo_mock.delete_by_user_id.assert_awaited_once_with("USER_a")
