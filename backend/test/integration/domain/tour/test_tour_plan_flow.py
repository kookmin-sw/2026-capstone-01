"""TourPlanService 통합 테스트.

실제 PostgreSQL + 실제 Repository 를 사용해 서비스 전체 플로우를 검증한다.
PlaceRepository 는 MongoDB 의존이라 Mock 으로 대체 (RDB 플로우만 검증).
"""

from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import select
import pytest

from app.domain.tour.service.tour_plan import TourPlanService
from app.domain.tour.service.exception import (
    TourPlanItemNotFoundError,
    TourPlanNotFoundError,
)
from app.domain.tour.model.tour_plan_item import TourPlanItem
from app.domain.tour.model.tour_plan import TourPlan
from app.domain.tour.dto.tour_plan import TourPlanItemCreateInput


pytestmark = pytest.mark.integration


# ──────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_place_doc():
    return {
        "place_id": "PLACE_INT_001",
        "display_name": "Integration Test Place",
        "address": "Seoul, Integration",
        "rating": 4.5,
    }


@pytest.fixture
def plan_service(uow, monkeypatch, fake_place_doc):
    """PlaceRepository 만 Mock — MongoDB 의존을 제거. 나머지는 실 DB."""
    fake_place_repo = MagicMock()
    fake_place_repo.find_by_place_id = AsyncMock(return_value=fake_place_doc)
    fake_place_repo.find_by_place_ids = AsyncMock(return_value=[fake_place_doc])

    monkeypatch.setattr(
        "app.domain.tour.service.tour_plan.PlaceRepository",
        lambda: fake_place_repo,
    )
    return TourPlanService(uow=uow)


# ──────────────────────────────────────────────────────────────────
# create_plan
# ──────────────────────────────────────────────────────────────────


class TestCreatePlanFlow:
    async def test_creates_plan_and_items(self, plan_service, seed_users, session_factory):
        (a,) = await seed_users(1)

        result = await plan_service.create_plan(
            user_id=a,
            title="Trip A",
            travel_days=2,
            items=[
                TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time="10:00"),
                TourPlanItemCreateInput(day_number=2, place_id="PLACE_INT_001", visit_time="11:00"),
            ],
        )

        assert result.user_id == a
        assert result.travel_days == 2
        assert len(result.items) == 2

        # DB 검증
        async with session_factory() as s:
            plan_rows = (await s.execute(select(TourPlan))).scalars().all()
            assert len(plan_rows) == 1
            assert plan_rows[0].title == "Trip A"

            item_rows = (await s.execute(select(TourPlanItem))).scalars().all()
            assert len(item_rows) == 2
            day_numbers = sorted(i.day_number for i in item_rows)
            assert day_numbers == [1, 2]


# ──────────────────────────────────────────────────────────────────
# get_plan / get_plans
# ──────────────────────────────────────────────────────────────────


class TestGetPlanFlow:
    async def test_returns_plan_with_items(self, plan_service, seed_users):
        (a,) = await seed_users(1)
        created = await plan_service.create_plan(
            user_id=a, title="X", travel_days=1,
            items=[TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None)],
        )

        result = await plan_service.get_plan(plan_id=created.plan_id, user_id=a)

        assert result.plan_id == created.plan_id
        assert len(result.items) == 1
        assert result.items[0].rating == 4.5  # MongoDB 라이브 매핑


    async def test_raises_not_found(self, plan_service, seed_users):
        (a,) = await seed_users(1)
        with pytest.raises(TourPlanNotFoundError):
            await plan_service.get_plan(plan_id="TP_ghost", user_id=a)


    async def test_raises_permission_for_other_user(self, plan_service, seed_users):
        a, b, _ = await seed_users(3)
        created = await plan_service.create_plan(
            user_id=a, title="A's plan", travel_days=1,
            items=[TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None)],
        )

        with pytest.raises(PermissionError):
            await plan_service.get_plan(plan_id=created.plan_id, user_id=b)


class TestGetPlansFlow:
    async def test_empty_for_new_user(self, plan_service, seed_users):
        (a,) = await seed_users(1)

        result = await plan_service.get_plans(user_id=a)

        assert result.plans == []


    async def test_returns_only_own_plans(self, plan_service, seed_users):
        a, b, _ = await seed_users(3)
        await plan_service.create_plan(
            user_id=a, title="A1", travel_days=1,
            items=[TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None)],
        )
        await plan_service.create_plan(
            user_id=b, title="B1", travel_days=1,
            items=[TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None)],
        )

        result = await plan_service.get_plans(user_id=a)

        assert len(result.plans) == 1
        assert result.plans[0].title == "A1"


# ──────────────────────────────────────────────────────────────────
# update_plan_title / delete_plan
# ──────────────────────────────────────────────────────────────────


class TestUpdatePlanTitleFlow:
    async def test_changes_title_and_updated_at(self, plan_service, seed_users, session_factory):
        (a,) = await seed_users(1)
        created = await plan_service.create_plan(
            user_id=a, title="Old", travel_days=1,
            items=[TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None)],
        )
        original_updated_at = created.updated_at

        await plan_service.update_plan_title(plan_id=created.plan_id, user_id=a, title="New")

        async with session_factory() as s:
            row = (await s.execute(select(TourPlan).where(TourPlan.plan_id == created.plan_id))).scalar_one()
            assert row.title == "New"
            assert row.updated_at >= original_updated_at  # 갱신됨


    async def test_clears_title(self, plan_service, seed_users, session_factory):
        (a,) = await seed_users(1)
        created = await plan_service.create_plan(
            user_id=a, title="Has Title", travel_days=1,
            items=[TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None)],
        )

        await plan_service.update_plan_title(plan_id=created.plan_id, user_id=a, title=None)

        async with session_factory() as s:
            row = (await s.execute(select(TourPlan).where(TourPlan.plan_id == created.plan_id))).scalar_one()
            assert row.title is None


class TestDeletePlanFlow:
    async def test_cascades_to_items(self, plan_service, seed_users, session_factory):
        (a,) = await seed_users(1)
        created = await plan_service.create_plan(
            user_id=a, title="X", travel_days=2,
            items=[
                TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None),
                TourPlanItemCreateInput(day_number=2, place_id="PLACE_INT_001", visit_time=None),
            ],
        )

        await plan_service.delete_plan(plan_id=created.plan_id, user_id=a)

        async with session_factory() as s:
            assert (await s.execute(select(TourPlan))).scalars().all() == []
            assert (await s.execute(select(TourPlanItem))).scalars().all() == []  # cascade


# ──────────────────────────────────────────────────────────────────
# add_day / remove_day
# ──────────────────────────────────────────────────────────────────


class TestAddDayFlow:
    async def test_increments_travel_days(self, plan_service, seed_users, session_factory):
        (a,) = await seed_users(1)
        created = await plan_service.create_plan(
            user_id=a, title="X", travel_days=3,
            items=[TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None)],
        )

        await plan_service.add_day(plan_id=created.plan_id, user_id=a)

        async with session_factory() as s:
            row = (await s.execute(select(TourPlan).where(TourPlan.plan_id == created.plan_id))).scalar_one()
            assert row.travel_days == 4


class TestRemoveDayFlow:
    async def test_clears_items_in_day_keeping_travel_days(
        self, plan_service, seed_users, session_factory,
    ):
        (a,) = await seed_users(1)
        created = await plan_service.create_plan(
            user_id=a, title="X", travel_days=3,
            items=[
                TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None),
                TourPlanItemCreateInput(day_number=2, place_id="PLACE_INT_001", visit_time=None),
                TourPlanItemCreateInput(day_number=3, place_id="PLACE_INT_001", visit_time=None),
            ],
        )

        await plan_service.remove_day(plan_id=created.plan_id, user_id=a, day_number=2)

        async with session_factory() as s:
            plan_row = (await s.execute(select(TourPlan).where(TourPlan.plan_id == created.plan_id))).scalar_one()
            # travel_days 유지 (gap 보존)
            assert plan_row.travel_days == 3

            items = (await s.execute(select(TourPlanItem).where(TourPlanItem.plan_id == created.plan_id))).scalars().all()
            day_numbers = sorted(i.day_number for i in items)
            assert day_numbers == [1, 3]  # day=2 만 사라짐 (gap)


    async def test_then_add_day_assigns_max_plus_one(
        self, plan_service, seed_users, session_factory,
    ):
        """remove_day 후 add_day 는 max+1 (gap 재사용 X)."""
        (a,) = await seed_users(1)
        created = await plan_service.create_plan(
            user_id=a, title="X", travel_days=3,
            items=[
                TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None),
                TourPlanItemCreateInput(day_number=2, place_id="PLACE_INT_001", visit_time=None),
                TourPlanItemCreateInput(day_number=3, place_id="PLACE_INT_001", visit_time=None),
            ],
        )

        await plan_service.remove_day(plan_id=created.plan_id, user_id=a, day_number=2)
        await plan_service.add_day(plan_id=created.plan_id, user_id=a)

        async with session_factory() as s:
            row = (await s.execute(select(TourPlan).where(TourPlan.plan_id == created.plan_id))).scalar_one()
            # travel_days = 4 (3+1, gap 재사용 X)
            assert row.travel_days == 4


    async def test_idempotent_for_empty_day(self, plan_service, seed_users):
        (a,) = await seed_users(1)
        created = await plan_service.create_plan(
            user_id=a, title="X", travel_days=3,
            items=[TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None)],
        )

        # day=2 는 비어있음 — 에러 없이 정상
        await plan_service.remove_day(plan_id=created.plan_id, user_id=a, day_number=2)


# ──────────────────────────────────────────────────────────────────
# add_item / remove_item / move_item / update_item
# ──────────────────────────────────────────────────────────────────


class TestAddItemFlow:
    async def test_appends_at_day_end(self, plan_service, seed_users, session_factory):
        (a,) = await seed_users(1)
        created = await plan_service.create_plan(
            user_id=a, title="X", travel_days=2,
            items=[TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None)],
        )

        added = await plan_service.add_item(
            plan_id=created.plan_id, user_id=a,
            day_number=1, place_id="PLACE_INT_001", visit_time="14:00",
        )

        async with session_factory() as s:
            items = (
                await s.execute(
                    select(TourPlanItem)
                    .where(TourPlanItem.plan_id == created.plan_id, TourPlanItem.day_number == 1)
                    .order_by(TourPlanItem.position.asc())
                )
            ).scalars().all()
            assert len(items) == 2
            # 새로 추가된 카드의 position 이 더 큼
            assert items[-1].item_id == added.item_id
            assert items[-1].position > items[0].position


class TestUpdateItemFlow:
    async def test_replaces_visit_time(self, plan_service, seed_users, session_factory):
        (a,) = await seed_users(1)
        created = await plan_service.create_plan(
            user_id=a, title="X", travel_days=1,
            items=[TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time="10:00")],
        )
        item_id = created.items[0].item_id

        await plan_service.update_item(
            item_id=item_id, user_id=a,
            place_id="PLACE_INT_001", visit_time="15:30",
            expected_plan_id=created.plan_id,
        )

        async with session_factory() as s:
            row = (await s.execute(select(TourPlanItem).where(TourPlanItem.item_id == item_id))).scalar_one()
            assert row.visit_time == "15:30"


    async def test_url_mismatch_raises_404_equivalent(self, plan_service, seed_users):
        (a,) = await seed_users(1)
        created = await plan_service.create_plan(
            user_id=a, title="X", travel_days=1,
            items=[TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None)],
        )
        item_id = created.items[0].item_id

        with pytest.raises(TourPlanItemNotFoundError):
            await plan_service.update_item(
                item_id=item_id, user_id=a,
                place_id="PLACE_INT_001", visit_time=None,
                expected_plan_id="TP_other",
            )


class TestMoveItemFlow:
    async def test_moves_to_other_day(self, plan_service, seed_users, session_factory):
        (a,) = await seed_users(1)
        created = await plan_service.create_plan(
            user_id=a, title="X", travel_days=2,
            items=[
                TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None),
            ],
        )
        item_id = created.items[0].item_id

        await plan_service.move_item(
            item_id=item_id, user_id=a,
            target_day_number=2, after_item_id=None,
        )

        async with session_factory() as s:
            row = (await s.execute(select(TourPlanItem).where(TourPlanItem.item_id == item_id))).scalar_one()
            assert row.day_number == 2


class TestRemoveItemFlow:
    async def test_deletes_single_item(self, plan_service, seed_users, session_factory):
        (a,) = await seed_users(1)
        created = await plan_service.create_plan(
            user_id=a, title="X", travel_days=1,
            items=[
                TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None),
                TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None),
            ],
        )
        target_id = created.items[0].item_id

        await plan_service.remove_item(item_id=target_id, user_id=a)

        async with session_factory() as s:
            remaining = (await s.execute(select(TourPlanItem).where(TourPlanItem.plan_id == created.plan_id))).scalars().all()
            assert len(remaining) == 1
            assert remaining[0].item_id != target_id
