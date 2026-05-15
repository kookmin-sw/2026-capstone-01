from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class PublicPlanItemResponse(BaseModel):
    """공개 share 응답의 카드 단건 (rating / photos 는 MongoDB 라이브)"""
    item_id: str = Field(..., description="카드 고유 ID")
    day_number: int = Field(..., description="여행 일차")
    position: float = Field(..., description="day 내 정렬 순서")
    place_id: str = Field(..., description="MongoDB Place ID")
    display_name: str = Field(..., description="장소 이름 (스냅샷)")
    address: str = Field(..., description="주소 (스냅샷)")
    visit_time: Optional[str] = Field(None, description="방문 시각 'HH:MM'")
    rating: Optional[float] = Field(None, description="별점 (MongoDB 라이브)")
    photos: List[str] = Field(default_factory=list, description="사진 URL 목록 (MongoDB 라이브, 없으면 빈 배열)")


class PublicPlanResponse(BaseModel):
    """공개 share 응답의 plan 상세 — 소유자 식별(user_id) 노출 X"""
    plan_id: str = Field(..., description="플랜 고유 ID")
    title: Optional[str] = Field(None, description="플랜 이름")
    travel_days: int = Field(..., description="부여된 day_number 의 최댓값")
    created_at: datetime = Field(..., description="저장 시각")
    updated_at: datetime = Field(..., description="마지막 편집 시각")
    items: List[PublicPlanItemResponse] = Field(..., description="카드 목록 (day, position 정렬)")
