"""FeedPopupService 단위 테스트 fixtures.

`access.resolve_viewer_visibilities` 의 friend/block 분기는 access 자체 단위 테스트 영역.
본 모듈은 popup 합성 흐름 (user 미존재 / 차단 propagate / feed 9개 limit / DTO 매핑) 만
검증 — `resolve_viewer_visibilities` 를 stub 으로 치환.
"""
from unittest.mock import AsyncMock
from test.unit.domain.feed.mock_factory import FakeUnitOfWork, make_mock_session
import pytest

from app.domain.feed.service.feed_popup import FeedPopupService
from app.domain.feed.model.feed_post import FeedVisibility


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture
def user_repo_mock():
    mock = AsyncMock()
    mock.find_by_id_with_profile.return_value = None  # 기본: 미존재
    return mock


@pytest.fixture
def feed_repo_mock():
    mock = AsyncMock()
    mock.find_by_owner.return_value = []
    return mock


@pytest.fixture
def visibilities_stub():
    """`resolve_viewer_visibilities` 의 default 결과 — 비친구로 시뮬레이션."""
    return [FeedVisibility.PUBLIC]


@pytest.fixture
def service(
    monkeypatch, mock_session,
    user_repo_mock, feed_repo_mock, visibilities_stub,
):
    """popup service — UserRepository / FeedPostRepository / access 모두 mock 주입."""
    monkeypatch.setattr(
        "app.domain.feed.service.feed_popup.UserRepository",
        lambda session: user_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.feed.service.feed_popup.FeedPostRepository",
        lambda session: feed_repo_mock,
    )

    async def _stub_resolve(session, *, viewer_id, owner_id):
        return visibilities_stub
    monkeypatch.setattr(
        "app.domain.feed.service.feed_popup.resolve_viewer_visibilities",
        _stub_resolve,
    )

    return FeedPopupService(uow=FakeUnitOfWork(mock_session))
