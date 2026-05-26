from app.util.share_token import decode_share_token
from app.domain.tour.service.exception import TourPlanNotFoundError
from app.domain.tour.repository.tour_plan import TourPlanRepository
from app.domain.tour.repository.place import PlaceRepository
from app.domain.tour.model.tour_plan_item import TourPlanItem
from app.domain.tour.model.tour_plan import TourPlan
from app.domain.public.dto.share import PublicPlanData, PublicPlanItemData
from app.database.session import UnitOfWork, transactional


class SharePlanService:
    """공개 share 토큰으로 plan 조회.

    - 인증 없음, ownership 검증 없음 (오로지 토큰 검증으로만 접근 제어)
    - TourPlanService 와 책임 분리: 권한 모델이 다른 별개 도메인
    - plan_repo / place_repo 만 재사용해 응답 빌드
    - 노출 응답에서 user_id 제외 (PublicPlanData 사용)
    """

    def __init__(self, uow: UnitOfWork):
        self.uow = uow
        self.place_repo = PlaceRepository()


    # ──────────────────── 공유 토큰으로 plan 조회 ────────────────────

    @transactional
    async def get_plan_by_token(self, share_token: str) -> PublicPlanData:
        """공유 토큰 디코드 → plan 조회 → 공개 응답 빌드.

        토큰 무효/만료 시 ShareTokenError, plan 없으면 TourPlanNotFoundError raise.
        """
        plan_id = decode_share_token(share_token)  # ShareTokenError 가 라우터에서 400/404 매핑

        plan_repo = TourPlanRepository(self._session)
        plan = await plan_repo.find_by_id_with_items(plan_id)
        if plan is None:
            raise TourPlanNotFoundError("존재하지 않는 플랜입니다.")

        items = sorted(plan.items, key=lambda i: (i.day_number, i.position))
        place_ids = list({i.place_id for i in items})
        raw_places = await self.place_repo.find_by_place_ids(place_ids)
        place_map = {p["place_id"]: p for p in raw_places}

        return self._to_public_plan_dto(plan, items, place_map)


    # ──────────────────── 내부 변환 유틸 ────────────────────

    @staticmethod
    def _to_public_plan_item_dto(item: TourPlanItem, rating, photos: list[str]) -> PublicPlanItemData:
        return PublicPlanItemData(
            item_id=item.item_id,
            day_number=item.day_number,
            position=item.position,
            place_id=item.place_id,
            display_name=item.display_name,
            address=item.address,
            visit_time=item.visit_time,
            rating=rating,
            photos=photos,
        )


    def _to_public_plan_dto(
        self,
        plan: TourPlan,
        items: list[TourPlanItem],
        place_map: dict[str, dict],
    ) -> PublicPlanData:
        item_dtos = []
        for i in items:
            raw = place_map.get(i.place_id)
            rating = raw.get("rating") if raw else None
            photos = (raw.get("photos") or []) if raw else []
            item_dtos.append(self._to_public_plan_item_dto(i, rating, photos))

        return PublicPlanData(
            plan_id=plan.plan_id,
            title=plan.title,
            travel_days=plan.travel_days,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
            items=item_dtos,
        )
