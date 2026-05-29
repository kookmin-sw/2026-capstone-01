"""TripmatePostLikeService 단위 테스트 fixtures.

좋아요 가시성 / 차단 검증은 본 service 책임이 아니므로 (tripmate 는 visibility 모델 없음),
post 존재 여부 + 중복 가드 + fan-out 통합 검증에 집중.
"""
from test.unit.domain.tripmate.tripmate_post_like_service.model_factory import (
    TripmatePostFactory,
    UserDetailInformFactory,
)
from test.unit.domain.tripmate.mock_factory import (
    FakeUnitOfWork,
    TripmatePostLikeRepositoryMockFactory,
    TripmatePostRepositoryMockFactory,
    UserDetailInformRepositoryMockFactory,
    make_mock_session,
    make_inbox_service_mock,
)
import pytest

from app.domain.tripmate.service.tripmate_post_like import TripmatePostLikeService


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture
def post_repo_mock():
    return TripmatePostRepositoryMockFactory.create()


@pytest.fixture
def like_repo_mock():
    return TripmatePostLikeRepositoryMockFactory.create()


@pytest.fixture
def detail_repo_mock():
    return UserDetailInformRepositoryMockFactory.create()


@pytest.fixture
def inbox_service_mock():
    return make_inbox_service_mock()


@pytest.fixture
def service(
    monkeypatch, mock_session,
    post_repo_mock, like_repo_mock, detail_repo_mock, inbox_service_mock,
):
    """service 가 RDB 트랜잭션 안에서 인스턴스화하는 모든 repo 를 mock 으로 치환.

    fan-out 은 `inbox_service_mock` 으로 호출만 검증, 실제 Mongo 비접근.
    """
    monkeypatch.setattr(
        "app.domain.tripmate.service.tripmate_post_like.TripmatePostRepository",
        lambda session: post_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.tripmate.service.tripmate_post_like.TripmatePostLikeRepository",
        lambda session: like_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.tripmate.service.tripmate_post_like.UserDetailInformRepository",
        lambda session: detail_repo_mock,
    )
    return TripmatePostLikeService(
        uow=FakeUnitOfWork(mock_session),
        inbox_service=inbox_service_mock,
    )


@pytest.fixture(autouse=True)
def reset_factories():
    """ID counter 격리 — 테스트 간 의존 방지."""
    TripmatePostFactory.reset_counter()
    UserDetailInformFactory.reset_counter()
    yield
    TripmatePostFactory.reset_counter()
    UserDetailInformFactory.reset_counter()
