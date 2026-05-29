from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.domain.tour.model.tour_plan_item import TourPlanItem


class TourPlanItemRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    # ──────────────────── Create ────────────────────

    async def save(self, item: TourPlanItem) -> TourPlanItem:
        """카드 단건 저장 (개별 추가 시)"""
        self.session.add(item)
        await self.session.flush()
        return item


    async def save_all(self, items: list[TourPlanItem]) -> list[TourPlanItem]:
        """카드 일괄 저장 (AI 응답 → 플랜 변환 시)"""
        if not items:
            return items
        self.session.add_all(items)
        await self.session.flush()
        return items


    # ──────────────────── Read (단건) ────────────────────

    async def find_by_id(self, item_id: str) -> Optional[TourPlanItem]:
        """카드 단건 조회 (수정/삭제 검증용)"""
        return await self.session.get(TourPlanItem, item_id)


    # ──────────────────── Read (목록) ────────────────────

    async def find_by_plan_id(self, plan_id: str) -> list[TourPlanItem]:
        """플랜의 모든 카드 조회 (day_number ASC, position ASC 정렬)

        - 카드 뷰 렌더링 및 추가/이동 시 이웃 position 계산용
        - day 기준 그룹화는 서비스 계층에서 처리
        """
        stmt = (
            select(TourPlanItem)
            .where(TourPlanItem.plan_id == plan_id)
            .order_by(TourPlanItem.day_number.asc(), TourPlanItem.position.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    # ──────────────────── Update ────────────────────

    async def update(self, item: TourPlanItem) -> TourPlanItem:
        """변경사항 flush (visit_time / position / day_number 변경 모두 동일)"""
        await self.session.flush()
        return item


    # ──────────────────── Delete ────────────────────

    async def delete(self, item: TourPlanItem) -> None:
        """카드 단건 삭제"""
        await self.session.delete(item)


    async def delete_by_plan_and_day(self, plan_id: str, day_number: int) -> None:
        """특정 plan/day 의 카드 일괄 삭제.

        remove_day 에서 사용 — N 번 단건 DELETE 대신 1 번 bulk DELETE.
        빈 day 에 대해서도 idempotent (0 rows 영향, 에러 없음).
        """
        stmt = delete(TourPlanItem).where(
            TourPlanItem.plan_id == plan_id,
            TourPlanItem.day_number == day_number,
        )
        await self.session.execute(stmt)
