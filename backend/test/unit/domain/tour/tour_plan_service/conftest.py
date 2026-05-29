from test.unit.domain.tour.tour_plan_service.model_factory import (
    TourPlanFactory,
    TourPlanItemFactory,
)
from test.unit.domain.tour.tour_plan_service.mock_factory import (
    FakeUnitOfWork,
    PlaceRepositoryMockFactory,
    TourPlanItemRepositoryMockFactory,
    TourPlanRepositoryMockFactory,
    make_mock_session,
)
import pytest

from app.domain.tour.service.tour_plan import TourPlanService


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
def item_repo_mock():
    return TourPlanItemRepositoryMockFactory.create()


@pytest.fixture
def place_repo_mock():
    return PlaceRepositoryMockFactory.create()


@pytest.fixture
def service(
    monkeypatch,
    mock_session,
    plan_repo_mock,
    item_repo_mock,
    place_repo_mock,
):
    """모든 의존성이 Mock 으로 주입된 TourPlanService.

    - TourPlanRepository / TourPlanItemRepository 는 service 메서드 안에서 인스턴스화되므로 monkeypatch.
    - PlaceRepository 는 __init__ 에서 인스턴스화되므로 monkeypatch 후 service 생성.
    """
    monkeypatch.setattr(
        "app.domain.tour.service.tour_plan.TourPlanRepository",
        lambda session: plan_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.tour.service.tour_plan.TourPlanItemRepository",
        lambda session: item_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.tour.service.tour_plan.PlaceRepository",
        lambda: place_repo_mock,
    )

    uow = FakeUnitOfWork(mock_session)
    return TourPlanService(uow=uow)
