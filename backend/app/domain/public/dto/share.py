from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class PublicPlanItemData:
    """공개 share 응답의 카드 단건 — TourPlanItemData 와 동일 필드.

    별도 클래스로 둔 이유: 내부 DTO 와 결합 끊고, 향후 노출 정책 변경 시 독립적으로 진화.
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
class PublicPlanData:
    """공개 share 응답의 plan 상세 — user_id 제외 (소유자 식별 노출 차단)."""
    plan_id: str
    title: Optional[str]
    travel_days: int
    created_at: datetime
    updated_at: datetime
    items: List[PublicPlanItemData]
