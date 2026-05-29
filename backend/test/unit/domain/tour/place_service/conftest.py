"""PlaceService 단위 테스트 fixtures.

PlaceRepository 는 인스턴스만 mock 치환 — `PlaceRepository.build_cursor` 같은 staticmethod
가 service 내부에서 직접 호출되므로 클래스 자체를 lambda 로 바꾸면 staticmethod 가 사라짐.
대신 service 인스턴스화 후 `service.place_repo` attribute 만 mock 으로 교체.
FavoritePlaceRepository 는 `@transactional` 안에서 인스턴스화되므로 클래스 monkeypatch.
"""
from test.unit.domain.tour.place_service.model_factory import PlaceRawFactory
from test.unit.domain.tour.place_service.mock_factory import (
    FakeUnitOfWork,
    FavoritePlaceRepositoryMockFactory,
    PlaceRepositoryMockFactory,
    make_mock_session,
)
import pytest

from app.domain.tour.service.place import PlaceService


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture
def place_repo_mock():
    return PlaceRepositoryMockFactory.create()


@pytest.fixture
def fav_repo_mock():
    return FavoritePlaceRepositoryMockFactory.create()


@pytest.fixture
def service(monkeypatch, mock_session, place_repo_mock, fav_repo_mock):
    monkeypatch.setattr(
        "app.domain.tour.service.place.FavoritePlaceRepository",
        lambda session: fav_repo_mock,
    )
    service = PlaceService(uow=FakeUnitOfWork(mock_session))
    service.place_repo = place_repo_mock
    return service


@pytest.fixture(autouse=True)
def reset_factories():
    PlaceRawFactory.reset_counter()
    yield
    PlaceRawFactory.reset_counter()
