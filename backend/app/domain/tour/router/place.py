from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from dependency_injector.wiring import Provide, inject

from app.domain.tour.service.place import PlaceService
from app.domain.tour.service.favorite_place import FavoritePlaceService
from app.domain.tour.service.tour_search_history import TourSearchHistoryService
from app.domain.tour.schema.place import (
    PlaceDetailResponse,
    PlaceResponse,
    PlaceListResponse,
    PlaceLocationResponse,
    PlacePriceRangeResponse,
    PlaceReviewResponse,
    FavoritePlaceRequest,
    FavoritePlaceResponse,
    FavoritePlaceListResponse,
)
from app.schema.common import MessageResponse
from app.core.logger import get_logger
from app.container import Container


router = APIRouter(prefix="/places", tags=["관광 장소"])
logger = get_logger("tour.place")

# 기본 좌표 (서울 광화문)
DEFAULT_LAT = 37.57594
DEFAULT_LNG = 126.97688


# ──────────────────── 장소 조회 ────────────────────


@router.get("")
@inject
async def get_places(
    request: Request,
    lat: Optional[float] = Query(None, description="위도 (미입력 시 광화문 기준)"),
    lng: Optional[float] = Query(None, description="경도 (미입력 시 광화문 기준)"),
    keyword: Optional[str] = Query(None, min_length=1, description="검색 키워드 (장소명, 카테고리)"),
    cursor: Optional[str] = Query(None, description="다음 페이지 커서"),
    max_distance: Optional[float] = Query(None, gt=0, description="최대 검색 반경 (미터)"),
    place_service: PlaceService = Depends(Provide[Container.place_service]),
    search_history_service: TourSearchHistoryService = Depends(Provide[Container.tour_search_history_service]),
) -> PlaceListResponse:
    """장소 조회 (거리순, 30개 페이지네이션)

    - 위도/경도 미입력 시 서울 광화문 기준
    - keyword 입력 시 장소명·카테고리 검색, 미입력 시 전체 조회
    - 로그인 유저의 즐겨찾기 여부 포함
    """
    actual_lat = lat if lat is not None else DEFAULT_LAT
    actual_lng = lng if lng is not None else DEFAULT_LNG
    user_id: str = request.state.user_id

    try:
        if keyword:
            # 검색어 저장 (첫 페이지 요청 시에만 저장)
            if not cursor:
                try:
                    await search_history_service.save_search(user_id=user_id, search_name=keyword)
                except Exception as e:
                    logger.warning("검색어 저장 키워드({}) 실패 (무시) - 에러: {}", keyword, e)

            result = await place_service.search_nearby_places(
                lat=actual_lat,
                lng=actual_lng,
                keyword=keyword,
                cursor=cursor,
                max_distance=max_distance,
                user_id=user_id,
            )
        else:
            result = await place_service.get_nearby_places(
                lat=actual_lat,
                lng=actual_lng,
                cursor=cursor,
                max_distance=max_distance,
                user_id=user_id,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("장소 조회 실패: {}", e)
        raise HTTPException(status_code=500, detail="장소 조회에 실패했습니다.")

    return PlaceListResponse(
        places=[_to_place_response(p) for p in result.places],
        next_cursor=result.next_cursor,
    )


# ──────────────────── 내부 변환 유틸 ────────────────────


def _to_place_response(place) -> PlaceResponse:
    """PlaceData DTO → PlaceResponse 스키마 변환"""
    return PlaceResponse(
        place_id=place.place_id,
        display_name=place.display_name,
        category=place.category,
        types=place.types,
        address=place.address,
        short_address=place.short_address,
        location=PlaceLocationResponse(lat=place.location.lat, lng=place.location.lng),
        rating=place.rating,
        rating_count=place.rating_count,
        price_level=place.price_level,
        price_range=PlacePriceRangeResponse(
            min=place.price_range.min, max=place.price_range.max
        ) if place.price_range else None,
        editorial_summary=place.editorial_summary,
        generative_summary=place.generative_summary,
        review_summary=place.review_summary,
        phone=place.phone,
        phone_international=place.phone_international,
        website=place.website,
        google_maps_url=place.google_maps_url,
        google_map_review_link=place.google_map_review_link,
        opening_hours=place.opening_hours,
        services=place.services,
        payment=place.payment,
        accessibility=place.accessibility,
        parking=place.parking,
        reviews=[
            PlaceReviewResponse(
                author=r.author,
                rating=r.rating,
                relative_time=r.relative_time,
                text=r.text,
            )
            for r in place.reviews
        ],
        photos=place.photos,
        distance=place.distance,
        is_favorite=place.is_favorite,
    )


# ──────────────────── 즐겨찾기 ────────────────────


@router.get("/favorites")
@inject
async def get_favorites(
    request: Request,
    favorite_place_service: FavoritePlaceService = Depends(Provide[Container.favorite_place_service]),
) -> FavoritePlaceListResponse:
    """내 즐겨찾기 장소 목록 조회 (최신순)"""
    user_id: str = request.state.user_id

    try:
        result = await favorite_place_service.get_favorites(user_id=user_id)
    except Exception as e:
        logger.error("즐겨찾기 목록 조회 실패: {}", e)
        raise HTTPException(status_code=500, detail="즐겨찾기 목록 조회에 실패했습니다.")

    return FavoritePlaceListResponse(
        favorites=[_to_favorite_response(f) for f in result.favorites],
        total_count=result.total_count,
    )


@router.post("/favorites", status_code=201)
@inject
async def add_favorite(
    request: Request,
    body: FavoritePlaceRequest,
    favorite_place_service: FavoritePlaceService = Depends(Provide[Container.favorite_place_service]),
) -> MessageResponse:
    """장소 즐겨찾기 추가"""
    user_id: str = request.state.user_id

    try:
        await favorite_place_service.add_favorite(user_id=user_id, place_id=body.place_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return MessageResponse(message="즐겨찾기에 추가되었습니다.")


@router.delete("/favorites/{place_id}")
@inject
async def remove_favorite(
    request: Request,
    place_id: str,
    favorite_place_service: FavoritePlaceService = Depends(Provide[Container.favorite_place_service]),
) -> MessageResponse:
    """장소 즐겨찾기 해제"""
    user_id: str = request.state.user_id

    try:
        await favorite_place_service.remove_favorite(user_id=user_id, place_id=place_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return MessageResponse(message="즐겨찾기가 해제되었습니다.")


# ──────────────────── 장소 단건 조회 ────────────────────


@router.get("/{place_id}")
@inject
async def get_place(
    request: Request,
    place_id: str,
    place_service: PlaceService = Depends(Provide[Container.place_service]),
) -> PlaceResponse:
    """place_id로 장소 단건 조회, 거리는 제공되지 않으므로 0으로 나옴."""
    user_id: str = request.state.user_id

    try:
        result = await place_service.get_place_by_id(place_id=place_id, user_id=user_id)
    except Exception as e:
        logger.error("장소 단건 조회 실패: {}", e)
        raise HTTPException(status_code=500, detail="장소 조회에 실패했습니다.")

    if result is None:
        raise HTTPException(status_code=404, detail="장소를 찾을 수 없습니다.")

    return _to_place_response(result)


# ──────────────────── 내부 변환 유틸 (즐겨찾기) ────────────────────


def _to_favorite_response(fav) -> FavoritePlaceResponse:
    """FavoritePlaceData DTO → FavoritePlaceResponse 스키마 변환"""
    place = fav.place
    return FavoritePlaceResponse(
        favorite_id=fav.favorite_id,
        created_at=fav.created_at.isoformat(),
        place=PlaceDetailResponse(
            place_id=place.place_id,
            display_name=place.display_name,
            category=place.category,
            types=place.types,
            address=place.address,
            short_address=place.short_address,
            location=PlaceLocationResponse(lat=place.location.lat, lng=place.location.lng),
            rating=place.rating,
            rating_count=place.rating_count,
            price_level=place.price_level,
            price_range=PlacePriceRangeResponse(
                min=place.price_range.min, max=place.price_range.max
            ) if place.price_range else None,
            editorial_summary=place.editorial_summary,
            generative_summary=place.generative_summary,
            review_summary=place.review_summary,
            phone=place.phone,
            phone_international=place.phone_international,
            website=place.website,
            google_maps_url=place.google_maps_url,
            google_map_review_link=place.google_map_review_link,
            opening_hours=place.opening_hours,
            services=place.services,
            payment=place.payment,
            accessibility=place.accessibility,
            parking=place.parking,
            reviews=[
                PlaceReviewResponse(
                    author=r.author,
                    rating=r.rating,
                    relative_time=r.relative_time,
                    text=r.text,
                )
                for r in place.reviews
            ],
            photos=place.photos,
        ),
    )
