from fastapi import APIRouter, Depends, HTTPException
from dependency_injector.wiring import Provide, inject

from app.util.share_token import ShareTokenError
from app.domain.tour.service.exception import TourPlanNotFoundError
from app.domain.public.service.share_plan import SharePlanService
from app.domain.public.schema.share import PublicPlanItemResponse, PublicPlanResponse
from app.container import Container


router = APIRouter(prefix="/share", tags=["공개 공유"])


# ──────────────────── 공유 토큰으로 플랜 조회 (인증 없음) ────────────────────


@router.get("/plan/{share_token}")
@inject
async def get_shared_plan(
    share_token: str,
    share_service: SharePlanService = Depends(Provide[Container.share_plan_service]),
) -> PublicPlanResponse:
    """공유 토큰으로 플랜 단건 조회 (공개, 인증 불필요).

    - 토큰 무효 / 만료 → 400
    - 토큰 디코드 성공했으나 plan 이 사라짐 → 404
    - 응답에서 소유자 식별(user_id) 정보는 제외
    """
    try:
        result = await share_service.get_plan_by_token(share_token=share_token)
    except ShareTokenError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TourPlanNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return _to_public_plan_response(result)


# ──────────────────── 내부 변환 유틸 ────────────────────


def _to_public_plan_response(plan) -> PublicPlanResponse:
    return PublicPlanResponse(
        plan_id=plan.plan_id,
        title=plan.title,
        travel_days=plan.travel_days,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        items=[
            PublicPlanItemResponse(
                item_id=i.item_id,
                day_number=i.day_number,
                position=i.position,
                place_id=i.place_id,
                display_name=i.display_name,
                address=i.address,
                visit_time=i.visit_time,
                rating=i.rating,
                photos=i.photos,
            )
            for i in plan.items
        ],
    )
