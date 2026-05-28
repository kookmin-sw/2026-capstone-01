from fastapi import APIRouter, HTTPException, Request, Depends
from dependency_injector.wiring import Provide, inject

from app.schema.common import MessageResponse
from app.domain.tour.service.tour_plan import TourPlanService
from app.domain.tour.service.exception import TourPlanNotFoundError, TourPlanItemNotFoundError
from app.domain.tour.schema.tour_plan import (
    CreatePlanRequest,
    UpdatePlanRequest,
    AddItemRequest,
    UpdateItemRequest,
    MoveItemRequest,
    PlanItemResponse,
    PlanDetailResponse,
    PlanSummaryResponse,
    PlanListResponse,
    ShareTokenResponse,
)
from app.domain.tour.dto.tour_plan import TourPlanItemCreateInput
from app.container import Container


router = APIRouter(prefix="/plans", tags=["여행 플랜"])


# ──────────────────── 플랜 CRUD ────────────────────


@router.post("", status_code=201)
@inject
async def create_plan(
    request: Request,
    body: CreatePlanRequest,
    plan_service: TourPlanService = Depends(Provide[Container.tour_plan_service]),
) -> PlanDetailResponse:
    """플랜 + 카드 일괄 생성

    (AI 추천 결과도 여기로)
    """
    user_id: str = request.state.user_id

    try:
        result = await plan_service.create_plan(
            user_id=user_id,
            title=body.title,
            travel_days=body.travel_days,
            items=[
                TourPlanItemCreateInput(
                    day_number=it.day_number,
                    place_id=it.place_id,
                    visit_time=it.visit_time,
                )
                for it in body.items
            ],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _to_plan_detail_response(result)


@router.get("")
@inject
async def get_plans(
    request: Request,
    plan_service: TourPlanService = Depends(Provide[Container.tour_plan_service]),
) -> PlanListResponse:
    """내 플랜 목록 조회 (최신순)"""
    user_id: str = request.state.user_id

    result = await plan_service.get_plans(user_id=user_id)
    return PlanListResponse(plans=[_to_plan_summary_response(p) for p in result.plans])


@router.get("/{plan_id}")
@inject
async def get_plan(
    request: Request,
    plan_id: str,
    plan_service: TourPlanService = Depends(Provide[Container.tour_plan_service]),
) -> PlanDetailResponse:
    """플랜 단건 조회"""
    user_id: str = request.state.user_id

    try:
        result = await plan_service.get_plan(plan_id=plan_id, user_id=user_id)
    except TourPlanNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return _to_plan_detail_response(result)


@router.patch("/{plan_id}")
@inject
async def update_plan(
    request: Request,
    plan_id: str,
    body: UpdatePlanRequest,
    plan_service: TourPlanService = Depends(Provide[Container.tour_plan_service]),
) -> PlanSummaryResponse:
    """플랜 메타 수정 (현재 title 만 지원)"""
    user_id: str = request.state.user_id

    try:
        result = await plan_service.update_plan_title(
            plan_id=plan_id, user_id=user_id, title=body.title,
        )
    except TourPlanNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return _to_plan_summary_response(result)


@router.post("/{plan_id}/share", status_code=201)
@inject
async def share_plan(
    request: Request,
    plan_id: str,
    plan_service: TourPlanService = Depends(Provide[Container.tour_plan_service]),
) -> ShareTokenResponse:
    """플랜 공유 토큰 발급 — JWT 로 plan_id 서명.

    이 토큰을 GET /api/public/share/plan/{share_token} 으로 호출하면 인증 없이
    plan 조회 가능. 만료 / 비밀키 회전으로 무효화.
    """
    user_id: str = request.state.user_id

    try:
        result = await plan_service.generate_share_token(plan_id=plan_id, user_id=user_id)
    except TourPlanNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return ShareTokenResponse(
        share_token=result.share_token,
        expires_at=result.expires_at,
    )


@router.post("/{plan_id}/days", status_code=201)
@inject
async def add_day(
    request: Request,
    plan_id: str,
    plan_service: TourPlanService = Depends(Provide[Container.tour_plan_service]),
) -> PlanSummaryResponse:
    """플랜에 빈 일차 추가 (travel_days += 1, 새 day = 기존 max + 1).

    travel_days 는 monotonic 증가 — remove_day 로 생긴 gap 은 재사용하지 않음.
    """
    user_id: str = request.state.user_id

    try:
        result = await plan_service.add_day(plan_id=plan_id, user_id=user_id)
    except TourPlanNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return _to_plan_summary_response(result)


@router.delete("/{plan_id}/days/{day_number}")
@inject
async def remove_day(
    request: Request,
    plan_id: str,
    day_number: int,
    plan_service: TourPlanService = Depends(Provide[Container.tour_plan_service]),
) -> MessageResponse:
    """플랜의 일차 삭제 — 해당 day 의 모든 카드 일괄 제거.

    설계: gap 보존 + 단조 증가 day_number.
    - travel_days 는 그대로 유지 (삭제된 day_number 자리에 gap)
    - 뒷 일차 당기기 X (cascading UPDATE 회피)
    - 이후 add_day 는 max+1 로 진행 (gap 재사용 X)
    """
    user_id: str = request.state.user_id

    try:
        await plan_service.remove_day(
            plan_id=plan_id, user_id=user_id, day_number=day_number,
        )
    except TourPlanNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        # 비즈니스 검증 실패 (day_number 범위 등) → 400
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return MessageResponse(message="일차가 삭제되었습니다.")


@router.delete("/{plan_id}")
@inject
async def delete_plan(
    request: Request,
    plan_id: str,
    plan_service: TourPlanService = Depends(Provide[Container.tour_plan_service]),
) -> MessageResponse:
    """플랜 삭제 (cascade 로 카드 자동 삭제)"""
    user_id: str = request.state.user_id

    try:
        await plan_service.delete_plan(plan_id=plan_id, user_id=user_id)
    except TourPlanNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return MessageResponse(message="플랜이 삭제되었습니다.")


# ──────────────────── 카드 편집 ────────────────────


@router.post("/{plan_id}/items", status_code=201)
@inject
async def add_item(
    request: Request,
    plan_id: str,
    body: AddItemRequest,
    plan_service: TourPlanService = Depends(Provide[Container.tour_plan_service]),
) -> PlanItemResponse:
    """카드 추가 (해당 day 의 맨 끝에 삽입)"""
    user_id: str = request.state.user_id

    try:
        result = await plan_service.add_item(
            plan_id=plan_id,
            user_id=user_id,
            day_number=body.day_number,
            place_id=body.place_id,
            visit_time=body.visit_time,
        )
    except TourPlanNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return _to_plan_item_response(result)


@router.put("/{plan_id}/items/{item_id}")
@inject
async def update_item(
    request: Request,
    plan_id: str,
    item_id: str,
    body: UpdateItemRequest,
    plan_service: TourPlanService = Depends(Provide[Container.tour_plan_service]),
) -> PlanItemResponse:
    """카드 교체 — place_id + visit_time 일괄 수정.

    place_id 변경 시 display_name / address 스냅샷도 새 Place 기준으로 갱신.
    day_number / position 변경은 /move 엔드포인트 사용.
    """
    user_id: str = request.state.user_id

    try:
        result = await plan_service.update_item(
            item_id=item_id,
            user_id=user_id,
            place_id=body.place_id,
            visit_time=body.visit_time,
            expected_plan_id=plan_id,
        )
    except TourPlanItemNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return _to_plan_item_response(result)


@router.patch("/{plan_id}/items/{item_id}/move")
@inject
async def move_item(
    request: Request,
    plan_id: str,
    item_id: str,
    body: MoveItemRequest,
    plan_service: TourPlanService = Depends(Provide[Container.tour_plan_service]),
) -> MessageResponse:
    """카드 이동 — target_day 의 after_item_id 다음 자리 (null 이면 맨 앞)"""
    user_id: str = request.state.user_id

    try:
        await plan_service.move_item(
            item_id=item_id,
            user_id=user_id,
            target_day_number=body.target_day_number,
            after_item_id=body.after_item_id,
            expected_plan_id=plan_id,
        )
    except TourPlanItemNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return MessageResponse(message="카드가 이동되었습니다.")


@router.delete("/{plan_id}/items/{item_id}")
@inject
async def remove_item(
    request: Request,
    plan_id: str,
    item_id: str,
    plan_service: TourPlanService = Depends(Provide[Container.tour_plan_service]),
) -> MessageResponse:
    """카드 삭제"""
    user_id: str = request.state.user_id

    try:
        await plan_service.remove_item(
            item_id=item_id,
            user_id=user_id,
            expected_plan_id=plan_id,
        )
    except TourPlanItemNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return MessageResponse(message="카드가 삭제되었습니다.")


# ──────────────────── 내부 변환 유틸 ────────────────────


def _to_plan_item_response(item) -> PlanItemResponse:
    return PlanItemResponse(
        item_id=item.item_id,
        day_number=item.day_number,
        position=item.position,
        place_id=item.place_id,
        display_name=item.display_name,
        address=item.address,
        visit_time=item.visit_time,
        rating=item.rating,
        photos=item.photos,
    )


def _to_plan_detail_response(plan) -> PlanDetailResponse:
    return PlanDetailResponse(
        plan_id=plan.plan_id,
        user_id=plan.user_id,
        title=plan.title,
        travel_days=plan.travel_days,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        items=[_to_plan_item_response(i) for i in plan.items],
    )


def _to_plan_summary_response(plan) -> PlanSummaryResponse:
    return PlanSummaryResponse(
        plan_id=plan.plan_id,
        title=plan.title,
        travel_days=plan.travel_days,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )
