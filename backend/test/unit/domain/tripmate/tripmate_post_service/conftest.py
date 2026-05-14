"""TripmatePostService 단위 테스트 fixtures.

의존성:
    - TripmatePostRepository / TripmatePostImageRepository / UserDetailInformRepository (RDB)
    - TripmatePostDraftService (DI 주입, draft 정리만 사용)
    - get_object_storage() (init 시점 + delete_post 안에서 재호출)
    - TripmateImageRepository (Mongo beanie, init 시점 + delete_post 안에서 재호출)
"""
import pytest

from app.domain.tripmate.service.tripmate_post import TripmatePostService

from test.unit.domain.tripmate.mock_factory import (
    FakeUnitOfWork,
    TripmatePostImageRepositoryMockFactory,
    TripmatePostRepositoryMockFactory,
    UserDetailInformRepositoryMockFactory,
    make_draft_service_mock,
    make_inbox_service_mock,
    make_mock_session,
    make_object_storage_mock,
    make_tripmate_image_mongo_repo_mock,
)
from test.unit.domain.tripmate.tripmate_post_service.model_factory import (
    TripmatePostFactory,
)


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture
def post_repo_mock():
    return TripmatePostRepositoryMockFactory.create()


@pytest.fixture
def image_repo_mock():
    return TripmatePostImageRepositoryMockFactory.create()


@pytest.fixture
def detail_repo_mock():
    return UserDetailInformRepositoryMockFactory.create()


@pytest.fixture
def draft_service_mock():
    return make_draft_service_mock()


@pytest.fixture
def storage_mock():
    return make_object_storage_mock()


@pytest.fixture
def mongo_image_repo_mock():
    return make_tripmate_image_mongo_repo_mock()


@pytest.fixture
def inbox_service_mock():
    """인박스 cascade 진입점 mock — `delete_post` 후 cascade_post_deleted 호출 검증용."""
    return make_inbox_service_mock()


@pytest.fixture
def service(
    monkeypatch, mock_session,
    post_repo_mock, image_repo_mock, detail_repo_mock,
    draft_service_mock, storage_mock, mongo_image_repo_mock,
    inbox_service_mock,
):
    """모든 외부 의존성 mock 치환 후 service 인스턴스화.

    `__init__` 에서 `get_object_storage()` / `TripmateImageRepository()` 를 호출하므로
    monkeypatch 우선, service 인스턴스화는 그 다음. `delete_post` 가 함수 내부에서
    `get_object_storage()` / `TripmateImageRepository()` 를 재호출 → 같은 monkeypatch 가 적용.
    """
    monkeypatch.setattr(
        "app.domain.tripmate.service.tripmate_post.TripmatePostRepository",
        lambda session: post_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.tripmate.service.tripmate_post.TripmatePostImageRepository",
        lambda session: image_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.tripmate.service.tripmate_post.UserDetailInformRepository",
        lambda session: detail_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.tripmate.service.tripmate_post.get_object_storage",
        lambda: storage_mock,
    )
    monkeypatch.setattr(
        "app.domain.tripmate.service.tripmate_post.TripmateImageRepository",
        lambda: mongo_image_repo_mock,
    )

    return TripmatePostService(
        uow=FakeUnitOfWork(mock_session),
        draft_service=draft_service_mock,
        inbox_service=inbox_service_mock,
    )


@pytest.fixture(autouse=True)
def reset_factories():
    TripmatePostFactory.reset_counter()
    yield
    TripmatePostFactory.reset_counter()
