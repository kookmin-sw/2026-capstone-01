from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class TourPlanItemCreateInput:
    """카드 생성 입력 (배치 저장용)"""
    day_number: int
    place_id: str
    visit_time: Optional[str] = None


@dataclass
class TourPlanItemData:
    """카드 단건 응답 DTO

    - rating / photos 는 MongoDB Place 에서 라이브 조회한 값 (스냅샷 아님)
    - display_name / address 는 RDB 스냅샷
    """
    item_id: str
    day_number: int
    position: float
    place_id: str
    display_name: str
    address: str
    visit_time: Optional[str]
    rating: Optional[float]
    photos: List[str]


@dataclass
class TourPlanData:
    """플랜 단건 응답 DTO (카드 포함)"""
    plan_id: str
    user_id: str
    title: Optional[str]
    travel_days: int
    created_at: datetime
    updated_at: datetime
    items: List[TourPlanItemData]


@dataclass
class TourPlanSummaryData:
    """플랜 목록 항목 DTO (메타만)"""
    plan_id: str
    title: Optional[str]
    travel_days: int
    created_at: datetime
    updated_at: datetime


@dataclass
class TourPlanListData:
    """플랜 목록 응답 DTO"""
    plans: List[TourPlanSummaryData]


@dataclass
class ShareTokenData:
    """플랜 공유 토큰 발급 응답 DTO"""
    share_token: str
    expires_at: datetime
