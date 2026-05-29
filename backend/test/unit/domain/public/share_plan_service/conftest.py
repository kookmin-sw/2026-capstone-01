from test.unit.domain.tour.tour_plan_service.model_factory import (
    TourPlanFactory,
    TourPlanItemFactory,
)
from test.unit.domain.tour.tour_plan_service.mock_factory import (
    FakeUnitOfWork,
    PlaceRepositoryMockFactory,
    TourPlanRepositoryMockFactory,
    make_mock_session,
)
import pytest

from app.domain.public.service.share_plan import SharePlanService


@pytest.fixture(autouse=True)
def reset_factories():
    TourPlanFactory.reset_counter()
    TourPlanItemFactory.reset_counter()
    yield
    TourPlanFactory.reset_counter()
    TourPlanItemFactory.reset_counter()


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture
def plan_repo_mock():
    return TourPlanRepositoryMockFactory.create()


@pytest.fixture
def place_repo_mock():
    return PlaceRepositoryMockFactory.create()


@pytest.fixture
def share_service(monkeypatch, mock_session, plan_repo_mock, place_repo_mock):
    """모든 의존성 Mock 인 SharePlanService."""
    monkeypatch.setattr(
        "app.domain.public.service.share_plan.TourPlanRepository",
        lambda session: plan_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.public.service.share_plan.PlaceRepository",
        lambda: place_repo_mock,
    )
    return SharePlanService(uow=FakeUnitOfWork(mock_session))
