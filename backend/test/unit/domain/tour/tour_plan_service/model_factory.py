from typing import List, Optional
from types import SimpleNamespace
from datetime import datetime, timezone


class TourPlanFactory:
    """TourPlan 모델 형태를 흉내내는 SimpleNamespace 생성.

    SQLAlchemy 인스트루멘테이션(backref/relationship 이벤트)을 우회해
    단위 테스트에서 세션 없이도 속성 접근/할당이 가능하게 한다.
    """

    _counter = 0

    @classmethod
    def create(
        cls,
        plan_id: Optional[str] = None,
        user_id: str = "USER_owner",
        title: Optional[str] = "Test Plan",
        travel_days: int = 3,
        items: Optional[List[SimpleNamespace]] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ) -> SimpleNamespace:
        cls._counter += 1
        now = datetime(2026, 5, 1, tzinfo=timezone.utc)
        return SimpleNamespace(
            plan_id=plan_id or f"TP_test_{cls._counter:04d}",
            user_id=user_id,
            title=title,
            travel_days=travel_days,
            items=items if items is not None else [],
            created_at=created_at or now,
            updated_at=updated_at or now,
        )


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0


class TourPlanItemFactory:
    """TourPlanItem 모델 형태를 흉내내는 SimpleNamespace 생성."""

    _counter = 0

    @classmethod
    def create(
        cls,
        item_id: Optional[str] = None,
        plan_id: str = "TP_test_0001",
        day_number: int = 1,
        position: float = 1024.0,
        place_id: str = "PLACE_TEST_001",
        display_name: str = "Test Place",
        address: str = "Seoul, Test",
        visit_time: Optional[str] = "10:00",
    ) -> SimpleNamespace:
        cls._counter += 1
        return SimpleNamespace(
            item_id=item_id or f"TPI_test_{cls._counter:04d}",
            plan_id=plan_id,
            day_number=day_number,
            position=position,
            place_id=place_id,
            display_name=display_name,
            address=address,
            visit_time=visit_time,
        )


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0


class PlaceDocFactory:
    """MongoDB Place 문서 (dict) 흉내."""

    @classmethod
    def create(
        cls,
        place_id: str = "PLACE_TEST_001",
        display_name: str = "Test Place",
        address: str = "Seoul, Test",
        rating: Optional[float] = 4.5,
    ) -> dict:
        return {
            "place_id": place_id,
            "display_name": display_name,
            "address": address,
            "rating": rating,
        }
