"""FavoritePlaceService 단위 테스트 fixtures.

PlaceRepository / FavoritePlaceRepository mock 은 place_service 의 mock_factory 재사용.
FavoritePlace 클래스도 service 가 직접 인스턴스화하므로 stub 으로 치환 (Phase 1 의 signup
패턴과 동일).
"""
from test.unit.domain.tour.place_service.mock_factory import (
    FakeUnitOfWork,
    FavoritePlaceRepositoryMockFactory,
    PlaceRepositoryMockFactory,
    make_mock_session,
)
from test.unit.domain.tour.favorite_place_service.model_factory import FavoritePlaceFactory
import pytest

from app.domain.tour.service.favorite_place import FavoritePlaceService


class _FavoritePlaceStub:
    """`FavoritePlace` SQLAlchemy 모델의 lightweight 대체 — `_sa_instance_state` 우회."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


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
    """PlaceRepository 인스턴스 직접 치환 + FavoritePlaceRepository / FavoritePlace stub."""
    monkeypatch.setattr(
        "app.domain.tour.service.favorite_place.FavoritePlaceRepository",
        lambda session: fav_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.tour.service.favorite_place.FavoritePlace",
        _FavoritePlaceStub,
    )
    service = FavoritePlaceService(uow=FakeUnitOfWork(mock_session))
    service.place_repo = place_repo_mock
    return service


@pytest.fixture(autouse=True)
def reset_factories():
    FavoritePlaceFactory.reset_counter()
    yield
    FavoritePlaceFactory.reset_counter()
