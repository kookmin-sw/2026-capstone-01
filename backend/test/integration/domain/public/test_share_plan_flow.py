"""SharePlanService 통합 테스트.

실 PostgreSQL + 실 Repository. PlaceRepository (MongoDB) 만 Mock.
플로우: tour 도메인에서 plan 생성 + share 토큰 발급 → public 도메인에서 토큰으로 조회.
"""

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.util.share_token import ShareTokenError, encode_share_token
from app.domain.tour.service.tour_plan import TourPlanService
from app.domain.tour.service.exception import TourPlanNotFoundError
from app.domain.tour.dto.tour_plan import TourPlanItemCreateInput
from app.domain.public.service.share_plan import SharePlanService


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
def services(uow, monkeypatch, fake_place_doc):
    """tour + share 서비스 한 쌍 — PlaceRepository 만 Mock."""
    fake_place_repo = MagicMock()
    fake_place_repo.find_by_place_id = AsyncMock(return_value=fake_place_doc)
    fake_place_repo.find_by_place_ids = AsyncMock(return_value=[fake_place_doc])

    monkeypatch.setattr(
        "app.domain.tour.service.tour_plan.PlaceRepository",
        lambda: fake_place_repo,
    )
    monkeypatch.setattr(
        "app.domain.public.service.share_plan.PlaceRepository",
        lambda: fake_place_repo,
    )
    return TourPlanService(uow=uow), SharePlanService(uow=uow)


# ──────────────────────────────────────────────────────────────────
# Share token 발급 → 공개 조회 플로우
# ──────────────────────────────────────────────────────────────────


class TestShareFlow:
    async def test_owner_generates_token_then_anyone_reads(self, services, seed_users):
        plan_service, share_service = services
        (a,) = await seed_users(1)

        # 소유자가 plan 생성 + 토큰 발급
        created = await plan_service.create_plan(
            user_id=a, title="Shared Trip", travel_days=2,
            items=[
                TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time="10:00"),
                TourPlanItemCreateInput(day_number=2, place_id="PLACE_INT_001", visit_time="14:00"),
            ],
        )
        token_data = await plan_service.generate_share_token(
            plan_id=created.plan_id, user_id=a,
        )

        # 토큰만으로 (인증 없이) 공개 조회
        result = await share_service.get_plan_by_token(share_token=token_data.share_token)

        assert result.plan_id == created.plan_id
        assert result.title == "Shared Trip"
        assert len(result.items) == 2
        # 노출 응답에 user_id 필드 없음
        assert not hasattr(result, "user_id")


    async def test_token_for_other_users_plan_works(self, services, seed_users):
        """발급은 본인 plan 만 가능하지만, 발급된 토큰은 누구나 사용 가능."""
        plan_service, share_service = services
        a, b, _ = await seed_users(3)

        created = await plan_service.create_plan(
            user_id=a, title="A's Trip", travel_days=1,
            items=[TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None)],
        )
        token_data = await plan_service.generate_share_token(
            plan_id=created.plan_id, user_id=a,
        )

        # b 가 토큰만 가지고 조회 (소유자가 아니지만 OK)
        result = await share_service.get_plan_by_token(share_token=token_data.share_token)
        assert result.plan_id == created.plan_id


    async def test_other_user_cannot_generate_token(self, services, seed_users):
        plan_service, _ = services
        a, b, _ = await seed_users(3)

        created = await plan_service.create_plan(
            user_id=a, title="A's Trip", travel_days=1,
            items=[TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None)],
        )

        with pytest.raises(PermissionError):
            await plan_service.generate_share_token(plan_id=created.plan_id, user_id=b)


    async def test_invalid_token_rejected(self, services, seed_users):
        _, share_service = services
        await seed_users(1)

        with pytest.raises(ShareTokenError):
            await share_service.get_plan_by_token(share_token="not-a-valid-jwt")


    async def test_token_for_deleted_plan_returns_not_found(self, services, seed_users):
        plan_service, share_service = services
        (a,) = await seed_users(1)

        created = await plan_service.create_plan(
            user_id=a, title="X", travel_days=1,
            items=[TourPlanItemCreateInput(day_number=1, place_id="PLACE_INT_001", visit_time=None)],
        )
        token_data = await plan_service.generate_share_token(
            plan_id=created.plan_id, user_id=a,
        )

        # 토큰 발급 후 plan 삭제 — 토큰 자체는 여전히 valid 한 JWT
        await plan_service.delete_plan(plan_id=created.plan_id, user_id=a)

        with pytest.raises(TourPlanNotFoundError):
            await share_service.get_plan_by_token(share_token=token_data.share_token)


    async def test_token_for_nonexistent_plan_returns_not_found(self, services, seed_users):
        _, share_service = services
        await seed_users(1)

        # 임의 plan_id 로 토큰 발급 (직접 인코드 — 해당 plan 은 DB 에 없음)
        token, _ = encode_share_token("TP_ghost_xxx")

        with pytest.raises(TourPlanNotFoundError):
            await share_service.get_plan_by_token(share_token=token)
