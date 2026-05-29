from typing import Optional
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domain.tour.model.tour_plan import TourPlan


class TourPlanRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    # ──────────────────── Create ────────────────────

    async def save(self, plan: TourPlan) -> TourPlan:
        """플랜 저장"""
        self.session.add(plan)
        await self.session.flush()
        return plan


    # ──────────────────── Read (단건) ────────────────────

    async def find_by_id(self, plan_id: str) -> Optional[TourPlan]:
        """플랜 단건 조회 (메타만, 권한 검증/수정 시)"""
        return await self.session.get(TourPlan, plan_id)


    async def find_by_id_with_items(self, plan_id: str) -> Optional[TourPlan]:
        """플랜 + 카드 목록 조회 (카드 뷰용, day/position 정렬)

        - selectinload 로 items 를 별도 IN 쿼리로 로드 → joinedload 보다 카디널리티 안전
        - items 정렬은 모델에서 보장하지 않으므로 호출 측에서 별도 정렬 필요 없도록
          여기서 선정렬 시키지 않고, 서비스에서 sort 하거나 `find_by_plan_id` 호출 권장
        """
        stmt = (
            select(TourPlan)
            .options(selectinload(TourPlan.items))
            .where(TourPlan.plan_id == plan_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


    # ──────────────────── Read (목록) ────────────────────

    async def find_all_by_user_id(self, user_id: str) -> list[TourPlan]:
        """유저의 플랜 목록 조회 (최신순)"""
        stmt = (
            select(TourPlan)
            .where(TourPlan.user_id == user_id)
            .order_by(TourPlan.updated_at.desc(), TourPlan.plan_id.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    # ──────────────────── Update ────────────────────

    async def update(self, plan: TourPlan) -> TourPlan:
        """변경사항 flush"""
        await self.session.flush()
        return plan


    # ──────────────────── Delete ────────────────────

    async def delete(self, plan: TourPlan) -> None:
        """플랜 삭제 (cascade 로 tour_plan_item 자동 삭제)"""
        await self.session.delete(plan)
