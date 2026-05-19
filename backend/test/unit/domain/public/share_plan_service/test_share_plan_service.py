"""SharePlanService 단위 테스트."""

from test.unit.domain.tour.tour_plan_service.model_factory import (
    PlaceDocFactory,
    TourPlanFactory,
    TourPlanItemFactory,
)
import pytest

from app.util.share_token import ShareTokenError, encode_share_token
from app.domain.tour.service.exception import TourPlanNotFoundError


@pytest.mark.unit
class TestGetPlanByToken:
    """Tests for SharePlanService.get_plan_by_token."""

    async def test_raises_on_invalid_token(self, share_service):
        with pytest.raises(ShareTokenError):
            await share_service.get_plan_by_token(share_token="garbage")


    async def test_raises_not_found_when_plan_missing(self, share_service, plan_repo_mock):
        token, _ = encode_share_token("TP_ghost")
        plan_repo_mock.find_by_id_with_items.return_value = None

        with pytest.raises(TourPlanNotFoundError):
            await share_service.get_plan_by_token(share_token=token)


    async def test_returns_public_plan_without_user_id(
        self, share_service, plan_repo_mock, place_repo_mock,
    ):
        items = [
            TourPlanItemFactory.create(day_number=1, position=1024.0, place_id="P1"),
            TourPlanItemFactory.create(day_number=1, position=2048.0, place_id="P2"),
        ]
        plan = TourPlanFactory.create(user_id="USER_owner", title="Public Plan", items=items)
        plan_repo_mock.find_by_id_with_items.return_value = plan
        place_repo_mock.find_by_place_ids.return_value = [
            PlaceDocFactory.create(place_id="P1", rating=4.0),
            PlaceDocFactory.create(place_id="P2", rating=3.5),
        ]
        token, _ = encode_share_token(plan.plan_id)

        result = await share_service.get_plan_by_token(share_token=token)

        assert result.plan_id == plan.plan_id
        assert result.title == "Public Plan"
        # PublicPlanData 에 user_id 필드 자체가 없음 (DTO 가 노출 안 함)
        assert not hasattr(result, "user_id")
        assert len(result.items) == 2
        ratings = {i.place_id: i.rating for i in result.items}
        assert ratings == {"P1": 4.0, "P2": 3.5}


    async def test_items_sorted_by_day_then_position(
        self, share_service, plan_repo_mock, place_repo_mock,
    ):
        # 의도적으로 뒤섞인 순서
        items = [
            TourPlanItemFactory.create(day_number=2, position=1024.0, place_id="P_d2"),
            TourPlanItemFactory.create(day_number=1, position=2048.0, place_id="P_d1b"),
            TourPlanItemFactory.create(day_number=1, position=1024.0, place_id="P_d1a"),
        ]
        plan = TourPlanFactory.create(items=items)
        plan_repo_mock.find_by_id_with_items.return_value = plan
        place_repo_mock.find_by_place_ids.return_value = [
            PlaceDocFactory.create(place_id="P_d1a"),
            PlaceDocFactory.create(place_id="P_d1b"),
            PlaceDocFactory.create(place_id="P_d2"),
        ]
        token, _ = encode_share_token(plan.plan_id)

        result = await share_service.get_plan_by_token(share_token=token)

        # day_number ASC, position ASC 정렬
        order = [(i.day_number, i.position) for i in result.items]
        assert order == [(1, 1024.0), (1, 2048.0), (2, 1024.0)]
