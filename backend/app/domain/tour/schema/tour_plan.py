from typing import List, Optional
import re
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


# HH:MM (24h) — 00:00 ~ 23:59
_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _validate_visit_time(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    if not _TIME_PATTERN.match(v):
        raise ValueError("visit_time 형식: HH:MM (24h)")
    return v


def _validate_title(v: Optional[str]) -> Optional[str]:
    """제목 정규화 — 양 끝 공백 제거 후 빈 값 거부.

    - None: 통과 (제목 미지정)
    - 공백만: ValueError (의도하지 않은 입력)
    - 정상: strip 결과 반환 (leading/trailing 공백 자동 제거)
    """
    if v is None:
        return v
    stripped = v.strip()
    if not stripped:
        raise ValueError("title 은 공백만으로 구성될 수 없습니다.")
    return stripped


# ──────────────────── Request ────────────────────


class CreatePlanItemInput(BaseModel):
    """플랜 생성 시 카드 1건 입력"""
    day_number: int = Field(..., ge=1, description="여행 일차 (1-indexed)")
    place_id: str = Field(..., min_length=1, max_length=255, description="MongoDB Place ID")
    visit_time: Optional[str] = Field(None, description="방문 시각 'HH:MM' (24h, 미지정 가능)")

    @field_validator("visit_time")
    @classmethod
    def _check_visit_time(cls, v: Optional[str]) -> Optional[str]:
        return _validate_visit_time(v)


class CreatePlanRequest(BaseModel):
    """플랜 생성 요청"""
    title: Optional[str] = Field(None, max_length=100, description="플랜 이름 (선택)")
    travel_days: int = Field(..., ge=1, description="여행 일수 (1 이상)")
    items: List[CreatePlanItemInput] = Field(..., min_length=1, description="카드 목록 (1개 이상)")

    @field_validator("title")
    @classmethod
    def _check_title(cls, v: Optional[str]) -> Optional[str]:
        return _validate_title(v)

    class Config:
        json_schema_extra = {
            "example": {
                "title": "서울 3일 여행",
                "travel_days": 3,
                "items": [
                    {"day_number": 1, "place_id": "ChIJExampleHongdaeCafe", "visit_time": "10:00"},
                    {"day_number": 1, "place_id": "ChIJExampleYeonnamPark", "visit_time": "12:00"},
                    {"day_number": 2, "place_id": "ChIJExampleBukchon", "visit_time": "10:00"},
                ],
            }
        }


class AddItemRequest(BaseModel):
    """카드 추가 요청 (해당 day 의 맨 끝에 삽입됨)"""
    day_number: int = Field(..., ge=1, description="여행 일차 (1-indexed)")
    place_id: str = Field(..., min_length=1, max_length=255, description="MongoDB Place ID")
    visit_time: Optional[str] = Field(None, description="방문 시각 'HH:MM' (24h, 미지정 가능)")

    @field_validator("visit_time")
    @classmethod
    def _check_visit_time(cls, v: Optional[str]) -> Optional[str]:
        return _validate_visit_time(v)


class MoveItemRequest(BaseModel):
    """카드 이동 요청"""
    target_day_number: int = Field(..., ge=1, description="이동 대상 여행 일차")
    after_item_id: Optional[str] = Field(
        None,
        description="이 카드 다음 자리로 이동. null 이면 target day 의 맨 앞.",
    )


class UpdatePlanRequest(BaseModel):
    """플랜 메타 수정 (현재 title 만 지원)

    - body 에 키가 반드시 있어야 함 (Field(...) required)
    - 값이 null 이면 플랜 이름 제거
    - 양 끝 공백은 자동 제거, 공백만으로 구성된 값은 거부
    """
    title: Optional[str] = Field(
        ...,
        max_length=100,
        description="플랜 이름. null 보내면 제목 제거.",
    )

    @field_validator("title")
    @classmethod
    def _check_title(cls, v: Optional[str]) -> Optional[str]:
        return _validate_title(v)


class UpdateItemRequest(BaseModel):
    """카드 교체 (PUT 의미 — 변경 가능한 필드 전부 명시)

    - place_id 가 바뀌면 display_name / address 스냅샷도 새 Place 기준으로 갱신됨
    - day_number / position 은 변경 안 함 (이동은 /move 엔드포인트 사용)
    """
    place_id: str = Field(..., min_length=1, max_length=255, description="MongoDB Place ID")
    visit_time: Optional[str] = Field(
        ...,
        description="방문 시각 'HH:MM' (24h). null 보내면 시각 미정.",
    )

    @field_validator("visit_time")
    @classmethod
    def _check_visit_time(cls, v: Optional[str]) -> Optional[str]:
        return _validate_visit_time(v)


# ──────────────────── Response ────────────────────


class PlanItemResponse(BaseModel):
    """카드 단건 응답 (rating / photos 는 MongoDB 라이브 조회값)"""
    item_id: str = Field(..., description="카드 고유 ID")
    day_number: int = Field(..., description="여행 일차")
    position: float = Field(..., description="day 내 정렬 순서")
    place_id: str = Field(..., description="MongoDB Place ID")
    display_name: str = Field(..., description="장소 이름 (스냅샷)")
    address: str = Field(..., description="주소 (스냅샷)")
    visit_time: Optional[str] = Field(None, description="방문 시각 'HH:MM'")
    rating: Optional[float] = Field(None, description="별점 (MongoDB 라이브, 없으면 null)")
    photos: List[str] = Field(default_factory=list, description="사진 URL 목록 (MongoDB 라이브, 없으면 빈 배열)")


class PlanDetailResponse(BaseModel):
    """플랜 상세 응답 (카드 포함)"""
    plan_id: str = Field(..., description="플랜 고유 ID")
    user_id: str = Field(..., description="작성자 ID")
    title: Optional[str] = Field(None, description="플랜 이름")
    travel_days: int = Field(..., description="여행 일수")
    created_at: datetime = Field(..., description="저장 시각")
    updated_at: datetime = Field(..., description="마지막 편집 시각")
    items: List[PlanItemResponse] = Field(..., description="카드 목록 (day_number, position 정렬)")


class PlanSummaryResponse(BaseModel):
    """플랜 목록 항목 응답 (메타만)"""
    plan_id: str = Field(..., description="플랜 고유 ID")
    title: Optional[str] = Field(None, description="플랜 이름")
    travel_days: int = Field(..., description="여행 일수")
    created_at: datetime = Field(..., description="저장 시각")
    updated_at: datetime = Field(..., description="마지막 편집 시각")


class PlanListResponse(BaseModel):
    """플랜 목록 응답"""
    plans: List[PlanSummaryResponse] = Field(..., description="플랜 목록 (최신순)")


class ShareTokenResponse(BaseModel):
    """플랜 공유 토큰 응답"""
    share_token: str = Field(..., description="JWT 공유 토큰. 공개 조회 URL: /api/public/share/plan/{token}")
    expires_at: datetime = Field(..., description="토큰 만료 시각")
