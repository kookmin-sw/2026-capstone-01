from test.unit.domain.tour.tour_plan_service.model_factory import (
    PlaceDocFactory,
    TourPlanFactory,
    TourPlanItemFactory,
)
import pytest

from app.domain.tour.service.tour_plan import (
    _MAX_POSITION_RETRY,
    _POSITION_SPACING,
    TourPlanService,
)
from app.domain.tour.service.exception import (
    TourPlanItemNotFoundError,
    TourPlanNotFoundError,
)
from app.domain.tour.dto.tour_plan import TourPlanItemCreateInput


# ──────────────────────────────────────────────────────────────────
# create_plan
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestCreatePlan:
    """Tests for TourPlanService.create_plan."""

    async def test_raises_when_travel_days_below_one(self, service):
        with pytest.raises(ValueError, match="travel_days"):
            await service.create_plan(
                user_id="USER_a", title=None, travel_days=0, items=[],
            )


    async def test_raises_when_items_empty(self, service):
        with pytest.raises(ValueError, match="카드가 1개 이상"):
            await service.create_plan(
                user_id="USER_a", title=None, travel_days=1, items=[],
            )


    async def test_raises_when_day_number_out_of_range(self, service):
        items = [TourPlanItemCreateInput(day_number=4, place_id="P1", visit_time=None)]
        with pytest.raises(ValueError, match="day_number"):
            await service.create_plan(
                user_id="USER_a", title=None, travel_days=3, items=items,
            )


    async def test_raises_when_place_not_found(self, service, place_repo_mock):
        place_repo_mock.find_by_place_ids.return_value = []  # MongoDB 에 없음
        items = [TourPlanItemCreateInput(day_number=1, place_id="GHOST", visit_time=None)]

        with pytest.raises(ValueError, match="존재하지 않는 장소"):
            await service.create_plan(
                user_id="USER_a", title=None, travel_days=1, items=items,
            )


    async def test_creates_plan_with_items_and_assigns_positions(
        self, service, place_repo_mock, plan_repo_mock,
    ):
        # day=1 에 2개, day=2 에 1개 — position 은 1024, 2048 (day=1) / 1024 (day=2)
        place_repo_mock.find_by_place_ids.return_value = [
            PlaceDocFactory.create(place_id="P1"),
            PlaceDocFactory.create(place_id="P2"),
            PlaceDocFactory.create(place_id="P3"),
        ]
        items = [
            TourPlanItemCreateInput(day_number=1, place_id="P1", visit_time="10:00"),
            TourPlanItemCreateInput(day_number=1, place_id="P2", visit_time="12:00"),
            TourPlanItemCreateInput(day_number=2, place_id="P3", visit_time="14:00"),
        ]

        result = await service.create_plan(
            user_id="USER_a", title="My Trip", travel_days=2, items=items,
        )

        # plan_repo.save 가 호출됐는지
        plan_repo_mock.save.assert_awaited_once()
        saved_plan = plan_repo_mock.save.await_args.args[0]
        assert saved_plan.user_id == "USER_a"
        assert saved_plan.title == "My Trip"
        assert saved_plan.travel_days == 2
        assert len(saved_plan.items) == 3

        # day-별 position 부여 (1024, 2048 / 1024)
        d1_items = [i for i in saved_plan.items if i.day_number == 1]
        d2_items = [i for i in saved_plan.items if i.day_number == 2]
        assert sorted(i.position for i in d1_items) == [_POSITION_SPACING, 2 * _POSITION_SPACING]
        assert [i.position for i in d2_items] == [_POSITION_SPACING]

        # 응답 DTO
        assert result.travel_days == 2
        assert len(result.items) == 3


# ──────────────────────────────────────────────────────────────────
# get_plan
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetPlan:
    """Tests for TourPlanService.get_plan."""

    async def test_raises_not_found_when_plan_missing(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id_with_items.return_value = None

        with pytest.raises(TourPlanNotFoundError):
            await service.get_plan(plan_id="TP_x", user_id="USER_a")


    async def test_raises_permission_when_not_owner(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id_with_items.return_value = TourPlanFactory.create(
            user_id="USER_other",
        )

        with pytest.raises(PermissionError):
            await service.get_plan(plan_id="TP_x", user_id="USER_a")


    async def test_returns_plan_with_items_and_rating(
        self, service, plan_repo_mock, place_repo_mock,
    ):
        items = [
            TourPlanItemFactory.create(day_number=1, position=1024.0, place_id="P1"),
            TourPlanItemFactory.create(day_number=1, position=2048.0, place_id="P2"),
        ]
        plan = TourPlanFactory.create(user_id="USER_a", items=items)
        plan_repo_mock.find_by_id_with_items.return_value = plan
        place_repo_mock.find_by_place_ids.return_value = [
            PlaceDocFactory.create(place_id="P1", rating=4.0),
            PlaceDocFactory.create(place_id="P2", rating=3.5),
        ]

        result = await service.get_plan(plan_id=plan.plan_id, user_id="USER_a")

        assert len(result.items) == 2
        # rating 라이브 매핑 확인
        ratings = {i.place_id: i.rating for i in result.items}
        assert ratings["P1"] == 4.0
        assert ratings["P2"] == 3.5


# ──────────────────────────────────────────────────────────────────
# get_plans
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetPlans:
    """Tests for TourPlanService.get_plans."""

    async def test_returns_empty_list_when_no_plans(self, service, plan_repo_mock):
        plan_repo_mock.find_all_by_user_id.return_value = []

        result = await service.get_plans(user_id="USER_a")

        assert result.plans == []


    async def test_returns_summaries(self, service, plan_repo_mock):
        plans = [
            TourPlanFactory.create(plan_id="TP_1", title="Plan 1"),
            TourPlanFactory.create(plan_id="TP_2", title="Plan 2"),
        ]
        plan_repo_mock.find_all_by_user_id.return_value = plans

        result = await service.get_plans(user_id="USER_a")

        assert len(result.plans) == 2
        assert {p.plan_id for p in result.plans} == {"TP_1", "TP_2"}


# ──────────────────────────────────────────────────────────────────
# update_plan_title
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestUpdatePlanTitle:
    """Tests for TourPlanService.update_plan_title."""

    async def test_raises_not_found(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id.return_value = None

        with pytest.raises(TourPlanNotFoundError):
            await service.update_plan_title(plan_id="TP_x", user_id="USER_a", title="X")


    async def test_raises_permission(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(user_id="USER_other")

        with pytest.raises(PermissionError):
            await service.update_plan_title(plan_id="TP_x", user_id="USER_a", title="X")


    async def test_updates_title_and_touches_updated_at(self, service, plan_repo_mock):
        plan = TourPlanFactory.create(user_id="USER_a", title="Old")
        original_updated_at = plan.updated_at
        plan_repo_mock.find_by_id.return_value = plan

        await service.update_plan_title(plan_id=plan.plan_id, user_id="USER_a", title="New")

        assert plan.title == "New"
        assert plan.updated_at != original_updated_at  # 명시적 touch
        plan_repo_mock.update.assert_awaited_once_with(plan)


    async def test_clears_title_when_null(self, service, plan_repo_mock):
        plan = TourPlanFactory.create(user_id="USER_a", title="Old")
        plan_repo_mock.find_by_id.return_value = plan

        await service.update_plan_title(plan_id=plan.plan_id, user_id="USER_a", title=None)

        assert plan.title is None


# ──────────────────────────────────────────────────────────────────
# add_day
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestAddDay:
    """Tests for TourPlanService.add_day."""

    async def test_raises_not_found(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id.return_value = None

        with pytest.raises(TourPlanNotFoundError):
            await service.add_day(plan_id="TP_x", user_id="USER_a")


    async def test_raises_permission(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(user_id="USER_other")

        with pytest.raises(PermissionError):
            await service.add_day(plan_id="TP_x", user_id="USER_a")


    async def test_increments_travel_days_and_touches_updated_at(self, service, plan_repo_mock):
        plan = TourPlanFactory.create(user_id="USER_a", travel_days=3)
        original_updated_at = plan.updated_at
        plan_repo_mock.find_by_id.return_value = plan

        await service.add_day(plan_id=plan.plan_id, user_id="USER_a")

        assert plan.travel_days == 4
        assert plan.updated_at != original_updated_at  # 명시적 touch (lazy refresh 회피)


# ──────────────────────────────────────────────────────────────────
# remove_day
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRemoveDay:
    """Tests for TourPlanService.remove_day."""

    async def test_raises_not_found(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id.return_value = None

        with pytest.raises(TourPlanNotFoundError):
            await service.remove_day(plan_id="TP_x", user_id="USER_a", day_number=1)


    async def test_raises_permission(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(user_id="USER_other")

        with pytest.raises(PermissionError):
            await service.remove_day(plan_id="TP_x", user_id="USER_a", day_number=1)


    async def test_raises_when_day_below_one(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(
            user_id="USER_a", travel_days=3,
        )
        with pytest.raises(ValueError, match="day_number"):
            await service.remove_day(plan_id="TP_x", user_id="USER_a", day_number=0)


    async def test_raises_when_day_above_travel_days(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(
            user_id="USER_a", travel_days=3,
        )
        with pytest.raises(ValueError, match="day_number"):
            await service.remove_day(plan_id="TP_x", user_id="USER_a", day_number=4)


    async def test_calls_bulk_delete_and_keeps_travel_days(
        self, service, plan_repo_mock, item_repo_mock,
    ):
        plan = TourPlanFactory.create(user_id="USER_a", travel_days=3)
        plan_repo_mock.find_by_id.return_value = plan

        await service.remove_day(plan_id=plan.plan_id, user_id="USER_a", day_number=2)

        # bulk DELETE 호출
        item_repo_mock.delete_by_plan_and_day.assert_awaited_once_with(plan.plan_id, 2)
        # travel_days 변화 없음 (gap 보존)
        assert plan.travel_days == 3
        # plan touch
        plan_repo_mock.update.assert_awaited_once_with(plan)


    async def test_idempotent_for_empty_day(
        self, service, plan_repo_mock, item_repo_mock,
    ):
        """빈 day 삭제도 에러 없이 정상 동작."""
        plan = TourPlanFactory.create(user_id="USER_a", travel_days=5)
        plan_repo_mock.find_by_id.return_value = plan

        # bulk delete returns None, no exception
        await service.remove_day(plan_id=plan.plan_id, user_id="USER_a", day_number=3)

        item_repo_mock.delete_by_plan_and_day.assert_awaited_once()


# ──────────────────────────────────────────────────────────────────
# delete_plan
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestDeletePlan:
    """Tests for TourPlanService.delete_plan."""

    async def test_raises_not_found(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id.return_value = None

        with pytest.raises(TourPlanNotFoundError):
            await service.delete_plan(plan_id="TP_x", user_id="USER_a")


    async def test_raises_permission(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(user_id="USER_other")

        with pytest.raises(PermissionError):
            await service.delete_plan(plan_id="TP_x", user_id="USER_a")


    async def test_calls_repository_delete(self, service, plan_repo_mock):
        plan = TourPlanFactory.create(user_id="USER_a")
        plan_repo_mock.find_by_id.return_value = plan

        await service.delete_plan(plan_id=plan.plan_id, user_id="USER_a")

        plan_repo_mock.delete.assert_awaited_once_with(plan)


# ──────────────────────────────────────────────────────────────────
# add_item
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestAddItem:
    """Tests for TourPlanService.add_item."""

    async def test_raises_not_found(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id.return_value = None

        with pytest.raises(TourPlanNotFoundError):
            await service.add_item(
                plan_id="TP_x", user_id="USER_a",
                day_number=1, place_id="P1", visit_time=None,
            )


    async def test_raises_permission(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(user_id="USER_other")

        with pytest.raises(PermissionError):
            await service.add_item(
                plan_id="TP_x", user_id="USER_a",
                day_number=1, place_id="P1", visit_time=None,
            )


    async def test_raises_when_day_out_of_range(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(
            user_id="USER_a", travel_days=3,
        )

        with pytest.raises(ValueError, match="day_number"):
            await service.add_item(
                plan_id="TP_x", user_id="USER_a",
                day_number=5, place_id="P1", visit_time=None,
            )


    async def test_raises_when_place_not_found(self, service, plan_repo_mock, place_repo_mock):
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(user_id="USER_a")
        place_repo_mock.find_by_place_id.return_value = None

        with pytest.raises(ValueError, match="존재하지 않는 장소"):
            await service.add_item(
                plan_id="TP_x", user_id="USER_a",
                day_number=1, place_id="GHOST", visit_time=None,
            )


    async def test_appends_at_day_end_when_empty_day(
        self, service, plan_repo_mock, item_repo_mock, place_repo_mock,
    ):
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(
            user_id="USER_a", travel_days=3,
        )
        place_repo_mock.find_by_place_id.return_value = PlaceDocFactory.create(place_id="P1")
        item_repo_mock.find_by_plan_id.return_value = []  # 빈 day

        result = await service.add_item(
            plan_id="TP_x", user_id="USER_a",
            day_number=1, place_id="P1", visit_time="10:00",
        )

        # 빈 day → position = _POSITION_SPACING
        item_repo_mock.save.assert_awaited_once()
        saved_item = item_repo_mock.save.await_args.args[0]
        assert saved_item.position == _POSITION_SPACING
        assert saved_item.day_number == 1
        assert saved_item.visit_time == "10:00"
        assert result.position == _POSITION_SPACING


    async def test_appends_at_day_end_after_existing_items(
        self, service, plan_repo_mock, item_repo_mock, place_repo_mock,
    ):
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(user_id="USER_a")
        place_repo_mock.find_by_place_id.return_value = PlaceDocFactory.create(place_id="P1")
        # 기존 카드: day=1 에 1024, 2048
        item_repo_mock.find_by_plan_id.return_value = [
            TourPlanItemFactory.create(day_number=1, position=1024.0),
            TourPlanItemFactory.create(day_number=1, position=2048.0),
            TourPlanItemFactory.create(day_number=2, position=1024.0),  # 다른 day
        ]

        await service.add_item(
            plan_id="TP_x", user_id="USER_a",
            day_number=1, place_id="P1", visit_time=None,
        )

        saved_item = item_repo_mock.save.await_args.args[0]
        # 마지막 (2048) + spacing = 3072
        assert saved_item.position == 2048.0 + _POSITION_SPACING


# ──────────────────────────────────────────────────────────────────
# update_item (PUT — 카드 교체)
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestUpdateItem:
    """Tests for TourPlanService.update_item."""

    async def test_raises_not_found_when_item_missing(self, service, item_repo_mock):
        item_repo_mock.find_by_id.return_value = None

        with pytest.raises(TourPlanItemNotFoundError):
            await service.update_item(
                item_id="TPI_x", user_id="USER_a",
                place_id="P1", visit_time=None,
            )


    async def test_raises_not_found_on_url_mismatch(self, service, item_repo_mock):
        item_repo_mock.find_by_id.return_value = TourPlanItemFactory.create(plan_id="TP_real")

        with pytest.raises(TourPlanItemNotFoundError):
            await service.update_item(
                item_id="TPI_x", user_id="USER_a",
                place_id="P1", visit_time=None,
                expected_plan_id="TP_other",
            )


    async def test_raises_permission(self, service, item_repo_mock, plan_repo_mock):
        item_repo_mock.find_by_id.return_value = TourPlanItemFactory.create(plan_id="TP_x")
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(user_id="USER_other")

        with pytest.raises(PermissionError):
            await service.update_item(
                item_id="TPI_x", user_id="USER_a",
                place_id="P1", visit_time=None,
            )


    async def test_raises_when_place_not_found(
        self, service, item_repo_mock, plan_repo_mock, place_repo_mock,
    ):
        item_repo_mock.find_by_id.return_value = TourPlanItemFactory.create(plan_id="TP_x")
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(user_id="USER_a")
        place_repo_mock.find_by_place_id.return_value = None

        with pytest.raises(ValueError, match="존재하지 않는 장소"):
            await service.update_item(
                item_id="TPI_x", user_id="USER_a",
                place_id="GHOST", visit_time=None,
            )


    async def test_replaces_place_id_and_refreshes_snapshot(
        self, service, item_repo_mock, plan_repo_mock, place_repo_mock,
    ):
        item = TourPlanItemFactory.create(
            plan_id="TP_x",
            place_id="P_old", display_name="Old Name", address="Old Addr", visit_time="10:00",
        )
        plan = TourPlanFactory.create(user_id="USER_a")
        item_repo_mock.find_by_id.return_value = item
        plan_repo_mock.find_by_id.return_value = plan
        place_repo_mock.find_by_place_id.return_value = PlaceDocFactory.create(
            place_id="P_new", display_name="New Name", address="New Addr", rating=4.2,
        )

        result = await service.update_item(
            item_id=item.item_id, user_id="USER_a",
            place_id="P_new", visit_time="14:00",
        )

        # 스냅샷 갱신
        assert item.place_id == "P_new"
        assert item.display_name == "New Name"
        assert item.address == "New Addr"
        assert item.visit_time == "14:00"
        # plan touch
        plan_repo_mock.update.assert_awaited_once_with(plan)
        # rating 라이브
        assert result.rating == 4.2


# ──────────────────────────────────────────────────────────────────
# move_item
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestMoveItem:
    """Tests for TourPlanService.move_item."""

    async def test_raises_not_found_when_item_missing(self, service, item_repo_mock):
        item_repo_mock.find_by_id.return_value = None

        with pytest.raises(TourPlanItemNotFoundError):
            await service.move_item(
                item_id="TPI_x", user_id="USER_a",
                target_day_number=1, after_item_id=None,
            )


    async def test_raises_permission(self, service, item_repo_mock, plan_repo_mock):
        item_repo_mock.find_by_id.return_value = TourPlanItemFactory.create(plan_id="TP_x")
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(user_id="USER_other")

        with pytest.raises(PermissionError):
            await service.move_item(
                item_id="TPI_x", user_id="USER_a",
                target_day_number=1, after_item_id=None,
            )


    async def test_raises_when_target_day_out_of_range(
        self, service, item_repo_mock, plan_repo_mock,
    ):
        item_repo_mock.find_by_id.return_value = TourPlanItemFactory.create(plan_id="TP_x")
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(
            user_id="USER_a", travel_days=3,
        )

        with pytest.raises(ValueError, match="day_number"):
            await service.move_item(
                item_id="TPI_x", user_id="USER_a",
                target_day_number=99, after_item_id=None,
            )


    async def test_moves_to_empty_day(
        self, service, item_repo_mock, plan_repo_mock,
    ):
        item = TourPlanItemFactory.create(plan_id="TP_x", day_number=1, position=1024.0)
        plan = TourPlanFactory.create(user_id="USER_a", travel_days=3)
        item_repo_mock.find_by_id.return_value = item
        plan_repo_mock.find_by_id.return_value = plan
        # day 2 는 비어있음
        item_repo_mock.find_by_plan_id.return_value = [item]  # 자기 자신만

        await service.move_item(
            item_id=item.item_id, user_id="USER_a",
            target_day_number=2, after_item_id=None,
        )

        assert item.day_number == 2
        assert item.position == _POSITION_SPACING


    async def test_moves_between_two_items(
        self, service, item_repo_mock, plan_repo_mock,
    ):
        moving = TourPlanItemFactory.create(plan_id="TP_x", day_number=1, position=4096.0)
        a = TourPlanItemFactory.create(plan_id="TP_x", day_number=2, position=1024.0)
        b = TourPlanItemFactory.create(plan_id="TP_x", day_number=2, position=2048.0)
        plan = TourPlanFactory.create(user_id="USER_a", travel_days=3)
        item_repo_mock.find_by_id.return_value = moving
        plan_repo_mock.find_by_id.return_value = plan
        item_repo_mock.find_by_plan_id.return_value = [moving, a, b]

        # day 2 의 a 다음 자리 (a, b 사이)
        await service.move_item(
            item_id=moving.item_id, user_id="USER_a",
            target_day_number=2, after_item_id=a.item_id,
        )

        assert moving.day_number == 2
        assert moving.position == (1024.0 + 2048.0) / 2  # midpoint


# ──────────────────────────────────────────────────────────────────
# remove_item
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRemoveItem:
    """Tests for TourPlanService.remove_item."""

    async def test_raises_not_found_when_item_missing(self, service, item_repo_mock):
        item_repo_mock.find_by_id.return_value = None

        with pytest.raises(TourPlanItemNotFoundError):
            await service.remove_item(item_id="TPI_x", user_id="USER_a")


    async def test_raises_not_found_on_url_mismatch(self, service, item_repo_mock):
        item_repo_mock.find_by_id.return_value = TourPlanItemFactory.create(plan_id="TP_real")

        with pytest.raises(TourPlanItemNotFoundError):
            await service.remove_item(
                item_id="TPI_x", user_id="USER_a", expected_plan_id="TP_other",
            )


    async def test_raises_permission(self, service, item_repo_mock, plan_repo_mock):
        item_repo_mock.find_by_id.return_value = TourPlanItemFactory.create(plan_id="TP_x")
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(user_id="USER_other")

        with pytest.raises(PermissionError):
            await service.remove_item(item_id="TPI_x", user_id="USER_a")


    async def test_deletes_item_and_touches_plan(
        self, service, item_repo_mock, plan_repo_mock,
    ):
        item = TourPlanItemFactory.create(plan_id="TP_x")
        plan = TourPlanFactory.create(user_id="USER_a")
        item_repo_mock.find_by_id.return_value = item
        plan_repo_mock.find_by_id.return_value = plan

        await service.remove_item(item_id=item.item_id, user_id="USER_a")

        item_repo_mock.delete.assert_awaited_once_with(item)
        plan_repo_mock.update.assert_awaited_once_with(plan)


# ──────────────────────────────────────────────────────────────────
# _compute_position (static method)
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestComputePosition:
    """Tests for TourPlanService._compute_position."""

    def test_empty_day_returns_default_spacing(self):
        assert TourPlanService._compute_position([], None) == _POSITION_SPACING


    def test_after_none_returns_first_half(self):
        items = [TourPlanItemFactory.create(position=1024.0)]
        assert TourPlanService._compute_position(items, None) == 512.0


    def test_after_last_returns_plus_spacing(self):
        items = [
            TourPlanItemFactory.create(item_id="A", position=1024.0),
            TourPlanItemFactory.create(item_id="B", position=2048.0),
        ]
        assert TourPlanService._compute_position(items, "B") == 2048.0 + _POSITION_SPACING


    def test_after_middle_returns_midpoint(self):
        items = [
            TourPlanItemFactory.create(item_id="A", position=1024.0),
            TourPlanItemFactory.create(item_id="B", position=2048.0),
            TourPlanItemFactory.create(item_id="C", position=3072.0),
        ]
        assert TourPlanService._compute_position(items, "A") == (1024.0 + 2048.0) / 2


    def test_raises_when_after_not_in_day(self):
        items = [TourPlanItemFactory.create(item_id="A", position=1024.0)]
        with pytest.raises(ValueError, match="after_item_id"):
            TourPlanService._compute_position(items, "GHOST")


# ──────────────────────────────────────────────────────────────────
# generate_share_token
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGenerateShareToken:
    """Tests for TourPlanService.generate_share_token."""

    async def test_raises_not_found(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id.return_value = None

        with pytest.raises(TourPlanNotFoundError):
            await service.generate_share_token(plan_id="TP_x", user_id="USER_a")


    async def test_raises_permission(self, service, plan_repo_mock):
        plan_repo_mock.find_by_id.return_value = TourPlanFactory.create(user_id="USER_other")

        with pytest.raises(PermissionError):
            await service.generate_share_token(plan_id="TP_x", user_id="USER_a")


    async def test_returns_token_and_expiry(self, service, plan_repo_mock):
        plan = TourPlanFactory.create(user_id="USER_a")
        plan_repo_mock.find_by_id.return_value = plan

        from app.util.share_token import decode_share_token

        result = await service.generate_share_token(plan_id=plan.plan_id, user_id="USER_a")

        assert result.share_token  # non-empty
        # 라운드트립 — 토큰 디코드 시 plan_id 복원
        assert decode_share_token(result.share_token) == plan.plan_id
        # 만료는 미래
        from datetime import datetime, timezone
        assert result.expires_at > datetime.now(timezone.utc)
