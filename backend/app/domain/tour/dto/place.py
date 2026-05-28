from typing import List, Optional
from dataclasses import dataclass


@dataclass
class PlaceLocationData:
    """좌표 DTO (API 친화적 lat/lng 형식)"""
    lat: float
    lng: float


@dataclass
class PlacePriceRangeData:
    """가격 범위 DTO"""
    min: Optional[str]
    max: Optional[str]


@dataclass
class PlaceReviewData:
    """리뷰 DTO"""
    author: str
    rating: Optional[int]
    relative_time: Optional[str]
    text: Optional[str]


@dataclass
class PlaceDetailData:
    """장소 상세 DTO (공통 베이스)"""

    # 식별
    place_id: str

    # 기본 정보
    display_name: str
    category: str
    types: List[str]
    address: str
    short_address: Optional[str]
    location: PlaceLocationData

    # 평가
    rating: Optional[float]
    rating_count: Optional[int]
    price_level: Optional[str]
    price_range: Optional[PlacePriceRangeData]

    # 요약
    editorial_summary: Optional[str]
    generative_summary: Optional[str]
    review_summary: Optional[str]

    # 연락처
    phone: Optional[str]
    phone_international: Optional[str]
    website: Optional[str]
    google_maps_url: Optional[str]
    google_map_review_link: Optional[str]

    # 운영 정보
    opening_hours: Optional[List[str]]
    services: Optional[List[str]]
    payment: Optional[List[str]]
    accessibility: Optional[List[str]]
    parking: Optional[List[str]]

    # 리뷰
    reviews: List[PlaceReviewData]

    # 사진 URL 목록
    photos: List[str]


@dataclass
class PlaceData(PlaceDetailData):
    """장소 조회 DTO (거리 + 즐겨찾기 포함)"""

    # 거리 (미터 단위, $geoNear 계산값)
    distance: float = 0.0

    # 즐겨찾기 여부 (즐겨찾기 O: True, X: None)
    is_favorite: Optional[bool] = None


@dataclass
class PlaceListData:
    """장소 목록 DTO (커서 페이지네이션)"""
    places: List[PlaceData]
    next_cursor: Optional[str]
