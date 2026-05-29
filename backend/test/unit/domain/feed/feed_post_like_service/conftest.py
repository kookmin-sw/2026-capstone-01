"""FeedPostLikeService 단위 테스트 fixtures.

`load_viewable_post` 의 가시성/차단 로직은 `access/test_load_viewable_post.py` 가 cover —
본 모듈은 helper 자체를 stub 으로 치환하고 좋아요 비즈니스 로직 (중복/취소/카운트) 만 검증.
"""
from unittest.mock import AsyncMock, MagicMock
from test.unit.domain.feed.mock_factory import FakeUnitOfWork, make_mock_session
import pytest
from datetime import datetime, timezone

from app.domain.feed.service.feed_post_like import FeedPostLikeService
from app.domain.feed.model.feed_post import FeedPost, FeedVisibility


def _mk_post(post_id="FDP_x", user_id="USER_owner"):
    post = MagicMock(spec=FeedPost)
    post.post_id = post_id
    post.user_id = user_id
    post.visibility = FeedVisibility.PUBLIC
    post.caption = None
    post.original_url = post.thumbnail_small_url = post.thumbnail_medium_url = "https://x"
    post.created_at = post.updated_at = datetime.now(timezone.utc)
    return post


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture
def like_repo_mock():
    mock = AsyncMock()
    mock.find_by_user_and_post.return_value = None  # 기본: 안 누른 상태
    mock.count_by_post.return_value = 0
    mock.find_with_user_by_post.return_value = []
    mock.save.side_effect = lambda like: like
    return mock


@pytest.fixture
def detail_repo_mock():
    """fan-out payload 합성 시 actor detail fetch 용. 결손(None) default — actor_name=""."""
    mock = AsyncMock()
    mock.find_by_user_id.return_value = None
    return mock


@pytest.fixture
def inbox_service_mock():
    """인박스 fan-out 진입점 mock — 호출 검증용. 본인→본인 skip 가드는 service 가 처리."""
    mock = AsyncMock()
    mock.notify_feed_like.return_value = None
    return mock


@pytest.fixture
def viewable_post_stub():
    """`load_viewable_post` 가 반환할 stub post — 가시성 통과 케이스 default."""
    return _mk_post()


@pytest.fixture
def service(
    monkeypatch, mock_session,
    like_repo_mock, detail_repo_mock, viewable_post_stub, inbox_service_mock,
):
    """가시성 통과 default 로 주입된 like service.

    개별 테스트가 `load_viewable_post` 의 raise 동작을 보고 싶으면 monkeypatch 직접 갱신.
    fan-out 은 `inbox_service_mock` 으로 호출만 검증, 실 Mongo 비접근.
    """
    monkeypatch.setattr(
        "app.domain.feed.service.feed_post_like.FeedPostLikeRepository",
        lambda session: like_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.feed.service.feed_post_like.UserDetailInformRepository",
        lambda session: detail_repo_mock,
    )
    # 기본: load_viewable_post 가 stub post 반환 (가시성 통과)
    async def _stub_load(session, *, viewer_id, post_id):
        return viewable_post_stub
    monkeypatch.setattr(
        "app.domain.feed.service.feed_post_like.load_viewable_post",
        _stub_load,
    )

    return FeedPostLikeService(
        uow=FakeUnitOfWork(mock_session),
        inbox_service=inbox_service_mock,
    )
