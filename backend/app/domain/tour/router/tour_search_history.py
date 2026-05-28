from typing import Optional
from fastapi import APIRouter, Request, Depends, Query
from dependency_injector.wiring import Provide, inject

from app.schema.common import MessageResponse
from app.domain.tour.service.tour_search_history import TourSearchHistoryService
from app.domain.tour.schema.tour_search_history import (
    TourSearchHistoryResponse, TourSearchHistoryListResponse,
)
from app.core.logger import get_logger
from app.container import Container


router = APIRouter(prefix="/search-history", tags=["관광 장소 검색 기록"])
logger = get_logger("tour.search_history")


# ──────────────────── 검색 기록 조회 ────────────────────

@router.get("")
@inject
async def get_search_histories(
    request: Request,
    search_service: TourSearchHistoryService = Depends(Provide[Container.tour_search_history_service]),
) -> TourSearchHistoryListResponse:
    """검색 기록 조회 (최신순, 최대 10개)"""
    user_id: str = request.state.user_id

    results = await search_service.get_search_histories(user_id)
    return TourSearchHistoryListResponse(
        histories=[
            TourSearchHistoryResponse(
                search_name=r.search_name,
                created_at=r.created_at,
            )
            for r in results
        ]
    )


# ──────────────────── 검색어 단건 삭제 ────────────────────

@router.delete("/one")
@inject
async def delete_search(
    request: Request,
    search_name: str = Query(..., min_length=1, description="삭제할 검색어"),
    search_service: TourSearchHistoryService = Depends(Provide[Container.tour_search_history_service]),
) -> MessageResponse:
    """특정 검색어 삭제"""
    user_id: str = request.state.user_id

    await search_service.delete_search(user_id=user_id, search_name=search_name)
    return MessageResponse(message="검색어가 삭제되었습니다.")


# ──────────────────── 검색 기록 전체 삭제 ────────────────────

@router.delete("")
@inject
async def delete_all_searches(
    request: Request,
    search_service: TourSearchHistoryService = Depends(Provide[Container.tour_search_history_service]),
) -> MessageResponse:
    """검색 기록 전체 삭제"""
    user_id: str = request.state.user_id

    await search_service.delete_all_searches(user_id)
    return MessageResponse(message="검색 기록이 모두 삭제되었습니다.")
