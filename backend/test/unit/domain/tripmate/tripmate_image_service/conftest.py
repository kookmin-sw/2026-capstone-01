"""TripmateImageService 단위 테스트 fixtures.

의존성:
    - TripmateImageRepository (Mongo, `__init__` 인스턴스화)
    - get_object_storage() (`__init__` 호출)
    - TripmatePostImageRepository (`@transactional` 안에서 인스턴스화 — cleanup 전용)
    - TripmateImage Document 클래스 (service 가 직접 인스턴스화)
    - TripmatePostDraft.find_one() Document classmethod (cleanup 전용)
    - generate_tripmate_image_id (id 생성 — 그대로 두어도 동작 OK)

beanie Document 들은 `init_beanie` 미호출 환경에서 인스턴스화 / classmethod 호출 시 에러
발생 가능 → stub 으로 치환. service 인스턴스화 시 self.image_repo / self.storage 는
attribute 직접 치환으로 mock 주입.
"""
from unittest.mock import AsyncMock
from test.unit.domain.tripmate.tripmate_image_service.model_factory import (
    TripmateImageFactory,
)
from test.unit.domain.tripmate.mock_factory import (
    FakeUnitOfWork,
    make_mock_session,
    make_object_storage_mock,
    make_tripmate_image_mongo_repo_full_mock,
    make_tripmate_post_image_repo_mock,
)
import pytest

from app.domain.tripmate.service.tripmate_image import TripmateImageService


class _ImageStub:
    """`TripmateImage` Document 의 lightweight 대체 — keyword 인스턴스화 attribute 부여."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture
def image_repo_mock():
    return make_tripmate_image_mongo_repo_full_mock()


@pytest.fixture
def post_image_repo_mock():
    return make_tripmate_post_image_repo_mock()


@pytest.fixture
def storage_mock():
    return make_object_storage_mock()


@pytest.fixture
def draft_find_one_mock(monkeypatch):
    """`TripmatePostDraft.find_one(...)` 의 awaitable 결과를 통제하는 AsyncMock.

    cleanup 흐름이 `await TripmatePostDraft.find_one({"user_id": ...})` 호출 → AsyncMock 은
    호출 시 coroutine 반환, await 시 `return_value` 를 돌려준다. 테스트가 return_value 를
    직접 set 하여 draft 존재/미존재 분기 시뮬레이션.
    """
    mock = AsyncMock(return_value=None)

    class _DraftStub:
        find_one = staticmethod(mock)

    monkeypatch.setattr(
        "app.domain.tripmate.service.tripmate_image.TripmatePostDraft",
        _DraftStub,
    )
    return mock


@pytest.fixture
def service(
    monkeypatch, mock_session,
    image_repo_mock, post_image_repo_mock, storage_mock, draft_find_one_mock,
):
    """모든 외부 의존성 mock 치환 후 service 인스턴스화.

    `TripmateImage` 는 service 가 직접 `TripmateImage(...)` 호출하므로 stub 으로 치환.
    `TripmatePostImageRepository` 는 `@transactional` 안에서 인스턴스화 → 클래스 monkeypatch.
    `image_repo` / `storage` 는 service 인스턴스 attribute 로 직접 치환.
    """
    monkeypatch.setattr(
        "app.domain.tripmate.service.tripmate_image.TripmateImage",
        _ImageStub,
    )
    monkeypatch.setattr(
        "app.domain.tripmate.service.tripmate_image.TripmatePostImageRepository",
        lambda session: post_image_repo_mock,
    )
    service = TripmateImageService(uow=FakeUnitOfWork(mock_session))
    service.image_repo = image_repo_mock
    service.storage = storage_mock
    return service


@pytest.fixture(autouse=True)
def reset_factories():
    TripmateImageFactory.reset_counter()
    yield
    TripmateImageFactory.reset_counter()
