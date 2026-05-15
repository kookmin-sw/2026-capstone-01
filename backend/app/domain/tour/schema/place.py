from typing import List, Optional
from pydantic import BaseModel, Field


# ──────────────────── Response ────────────────────


class PlaceLocationResponse(BaseModel):
    lat: float = Field(..., description="위도")
    lng: float = Field(..., description="경도")


class PlacePriceRangeResponse(BaseModel):
    min: Optional[str] = Field(None, description="최소 가격 (예: '10000 KRW')")
    max: Optional[str] = Field(None, description="최대 가격 (예: '20000 KRW')")


class PlaceReviewResponse(BaseModel):
    author: str = Field(..., description="리뷰 작성자")
    rating: Optional[int] = Field(None, description="별점 (1~5)")
    relative_time: Optional[str] = Field(None, description="작성 시점 (예: '8달 전')")
    text: Optional[str] = Field(None, description="리뷰 본문")


class PlaceDetailResponse(BaseModel):
    """장소 상세 정보 (공통 베이스)"""
    place_id: str = Field(..., description="Google Places 고유 ID")
    display_name: str = Field(..., description="장소 이름")
    category: str = Field(..., description="한글 카테고리명 (예: '한식당')")
    types: List[str] = Field(..., description="Google Places 타입 태그")
    address: str = Field(..., description="전체 주소")
    short_address: Optional[str] = Field(None, description="간략 주소")
    location: PlaceLocationResponse = Field(..., description="좌표")
    rating: Optional[float] = Field(None, description="평균 별점 (1.0~5.0)")
    rating_count: Optional[int] = Field(None, description="리뷰 수")
    price_level: Optional[str] = Field(None, description="가격 수준 (예: '보통 ($$)')")
    price_range: Optional[PlacePriceRangeResponse] = Field(None, description="가격 범위")
    editorial_summary: Optional[str] = Field(None, description="Google 편집자 요약")
    generative_summary: Optional[str] = Field(None, description="AI 생성 요약")
    review_summary: Optional[str] = Field(None, description="리뷰 요약")
    phone: Optional[str] = Field(None, description="국내 전화번호")
    phone_international: Optional[str] = Field(None, description="국제 전화번호")
    website: Optional[str] = Field(None, description="웹사이트 URL")
    google_maps_url: Optional[str] = Field(None, description="Google Maps 장소 페이지 URL")
    google_map_review_link: Optional[str] = Field(None, description="Google Maps 리뷰 페이지 URL")
    opening_hours: Optional[List[str]] = Field(None, description="요일별 영업시간")
    services: Optional[List[str]] = Field(None, description="제공 서비스")
    payment: Optional[List[str]] = Field(None, description="결제 수단")
    accessibility: Optional[List[str]] = Field(None, description="접근성 정보")
    parking: Optional[List[str]] = Field(None, description="주차 정보")
    reviews: List[PlaceReviewResponse] = Field(..., description="리뷰 목록")
    photos: List[str] = Field(default_factory=list, description="사진 URL 목록 (없으면 빈 배열)")


class PlaceResponse(PlaceDetailResponse):
    """장소 조회 응답 (거리 + 즐겨찾기 포함)"""
    distance: float = Field(..., description="현재 위치로부터 거리 (미터)")
    is_favorite: Optional[bool] = Field(None, description="즐겨찾기 여부 (즐겨찾기 X - null, 즐겨찾기 O - true)")


class PlaceListResponse(BaseModel):
    places: List[PlaceResponse] = Field(..., description="장소 목록")
    next_cursor: Optional[str] = Field(None, description="다음 페이지 커서 (마지막 페이지면 null)")


# ──────────────────── 즐겨찾기 ────────────────────


class FavoritePlaceRequest(BaseModel):
    place_id: str = Field(..., description="Google Places 고유 ID")


class FavoritePlaceResponse(BaseModel):
    favorite_id: str = Field(..., description="즐겨찾기 고유 ID")
    created_at: str = Field(..., description="즐겨찾기 등록 시각")
    place: PlaceDetailResponse = Field(..., description="장소 상세 정보")


class FavoritePlaceListResponse(BaseModel):
    favorites: List[FavoritePlaceResponse] = Field(..., description="즐겨찾기 목록")
    total_count: int = Field(..., description="즐겨찾기 총 개수")
