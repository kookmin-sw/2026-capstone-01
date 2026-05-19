"""TripmatePostDraftService 단위 테스트 fixtures.

beanie Document `TripmatePostDraft` 는 `init_beanie` 미호출 환경에서 인스턴스화 시
`CollectionWasNotInitialized` 가 raise → service 가 직접 인스턴스화하므로 stub 으로 치환.
TripmatePostDraftRepository 는 `__init__` 에서 인스턴스화 → service 인스턴스 생성 후
attribute 직접 치환 (notification 패턴 동일).
"""
from unittest.mock import AsyncMock
import pytest

from app.domain.tripmate.service.tripmate_post_draft import TripmatePostDraftService


class _DraftStub:
    """`TripmatePostDraft` Document 의 lightweight 대체 — keyword 인스턴스화 attribute 부여."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def draft_repo_mock():
    mock = AsyncMock()
    mock.upsert.side_effect = lambda d: d
    mock.find_by_user_id.return_value = None
    mock.delete_by_user_id.return_value = None
    return mock


@pytest.fixture
def service(monkeypatch, draft_repo_mock):
    monkeypatch.setattr(
        "app.domain.tripmate.service.tripmate_post_draft.TripmatePostDraft",
        _DraftStub,
    )
    service = TripmatePostDraftService()
    service.draft_repo = draft_repo_mock
    return service
