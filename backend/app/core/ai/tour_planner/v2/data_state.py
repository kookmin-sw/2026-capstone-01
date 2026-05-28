"""Tour Planner v2 데이터 단일 진입점.

- 사용자 입력 / 최종 출력 Pydantic 모델
- LangGraph 상태 TypedDict

서비스가 외국인 한국 여행자 대상이라 모든 사용자 노출 텍스트(LLM 출력 포함)는
영어로 통일한다. Pydantic Field의 description과 class docstring은
``with_structured_output``을 통해 LLM에 schema로 전달되므로 영어로 작성하고,
디버깅 가독성을 위해 옆에 한국어 inline 주석을 둔다.
"""

from typing import List, Literal, Optional, TypedDict
from pydantic import BaseModel, Field


# ──────────────────── 사용자 입력 (영어 코드) ────────────────────
# 한국어 주석은 디버깅 시 의미 추적용이며, prompt/응답에는 노출되지 않는다.

# 음식 옵션 — halal: 할랄, vegetarian: 채식, any: 상관없음
FoodPreference = Literal["halal", "vegetarian", "any"]

# 이동 수단 — public_transport: 대중교통
Transport = Literal["public_transport"]

# 동행 유형
Companion = Literal[
    "solo",                 # 혼자
    "couple",               # 연인
    "spouse",               # 부부
    "friends_colleagues",   # 친구·동료
    "family_parents",       # 가족(부모님)
    "family_with_kids",     # 가족(아이 동반)
]

# 여행 스타일 (다중 선택)
TravelStyle = Literal[
    "activity",             # 체험·액티비티
    "famous_attractions",   # 유명 관광지
    "healing",              # 휴양·힐링
    "culture_history",      # 관광·문화·역사
    "shopping",             # 쇼핑
    "food_tour",            # 맛집 탐방
    "photo_aesthetic",      # 사진·감성
    "festival_event",       # 축제·이벤트
]

# 일정 밀도 — relaxed: 널널하게, packed: 빡빡하게
ScheduleDensity = Literal["relaxed", "packed"]


# ──────────────────── 사용자 입력 모델 ────────────────────


class TourDayInput(BaseModel):
    """Per-day user input."""  # 일자별 사용자 입력

    departure_cluster: str = Field(description="Departure cluster (English standard name).")  # 출발 권역
    arrival_cluster: str = Field(description="Arrival cluster (English standard name).")  # 도착 권역
    additional_place_id: Optional[str] = Field(None, description="place_id of a required must-visit place. None if not specified.")  # 필수 포함 장소 place_id
    transport: Transport = Field(description="Transportation mode.")  # 이동 수단
    start_time: str = Field(description="Start time in HH:MM (24h).")  # 시작 시각
    end_time: str = Field(description="End time in HH:MM (24h).")  # 종료 시각
    companion: Companion = Field(description="Companion type.")  # 동행 유형
    budget_per_person_krw: int = Field(description="Per-person budget in KRW.")  # 1인 예산 (원)
    styles: List[TravelStyle] = Field(description="Travel styles (multi-select).")  # 여행 스타일
    schedule_density: ScheduleDensity = Field(description="Schedule density.")  # 일정 밀도


class TourPlannerInput(BaseModel):
    """Full planner input."""  # 전체 입력

    travel_days: int = Field(ge=1, le=3, description="Number of travel days (1-3).")  # 여행 일수
    food_preference: FoodPreference = Field(description="Food preference option.")  # 음식 옵션
    days: List[TourDayInput] = Field(description="Per-day inputs. len(days) MUST equal travel_days.")  # 일자별 입력


# ──────────────────── 최종 출력 모델 ────────────────────


class TourPlanLocation(BaseModel):
    """Coordinate."""  # 좌표

    lat: float = Field(description="Latitude.")  # 위도
    lng: float = Field(description="Longitude.")  # 경도


class TourTimelineSlot(BaseModel):
    """Timeline slot."""  # 타임라인 슬롯

    time: str = Field(description="Time in HH:MM (24h).")  # 시각
    place_id: str = Field(description="place_id at this slot. MUST reference an existing place in `places` (or the Required Additional Place). Transit between venues is described in the `movements` array, not as a timeline slot.")  # 해당 슬롯 place_id (필수)
    title: str = Field(description="Slot description in English. Format: 'Place Name → Activity' (e.g. 'Bukchon Hanok Village → Stroll the alleys').")  # 슬롯 설명


class TourPlaceDetail(BaseModel):
    """Place detail."""  # 장소 상세

    place_id: str = Field(description="Google Places unique ID.")  # Google Places 고유 ID
    display_name: str = Field(description="Place name.")  # 장소 이름
    category: str = Field(description="Place category.")  # 카테고리
    address: str = Field(description="Address.")  # 주소
    location: TourPlanLocation = Field(description="Coordinate.")  # 좌표
    rating: Optional[float] = Field(None, description="Average rating.")  # 평균 별점
    reason: str = Field(description="Reason and highlights in English (2-3 sentences).")  # 추천 이유
    estimated_cost_krw: int = Field(ge=0, description="Estimated per-person spend in KRW. Use 0 for free places (parks, public streets, free landmarks).")  # 예상 1인 지출 (무료=0)
    stay_minutes: int = Field(gt=0, description="Recommended stay in minutes. Typical: meals 60-90, cafes 60, attractions 60-120, shopping 60, nightlife 90.")  # 권장 체류 시간 (양수)
    is_additional: bool = Field(False, description="True if this is the user-required must-visit place.")  # 추가 장소 여부
    photos: List[str] = Field(default_factory=list, description="Photo URLs. DO NOT POPULATE — leave as []. Server overwrites this from the database after your response.")  # 사진 URL (서버가 find_nearby 결과로 강제 주입; LLM은 채우지 말 것)


class TourMovementHop(BaseModel):
    """Movement hop between two places."""  # 이동 흐름

    from_place: str = Field(description="Origin place name.")  # 출발 장소 이름
    to_place: str = Field(description="Destination place name.")  # 도착 장소 이름
    method: str = Field(description="Movement description in English (e.g. 'Subway Line 2 → 5 min walk').")  # 이동 방법


class TourBudgetItem(BaseModel):
    """Budget breakdown item."""  # 예산 항목

    label: str = Field(description="Item label in English (e.g. 'Lunch', 'Cafe', 'Admission').")  # 항목명
    amount_krw: int = Field(description="Amount in KRW.")  # 금액


class TourDayPlan(BaseModel):
    """Per-day final plan."""  # 일자별 최종 플랜

    day: int = Field(description="Day number (1-indexed).")  # 여행 일차
    timeline: List[TourTimelineSlot] = Field(description="Time-based itinerary, ordered by time.")  # 시간 기반 동선
    places: List[TourPlaceDetail] = Field(description="Detailed list of selected places.")  # 장소 상세 목록
    movements: List[TourMovementHop] = Field(description="Movement hops between adjacent places.")  # 이동 흐름
    budget_breakdown: List[TourBudgetItem] = Field(description="Budget items. Sum MUST NOT exceed budget_per_person_krw.")  # 예산 분배
    budget_total_krw: int = Field(description="Total budget in KRW (sum of budget_breakdown).")  # 예산 합계
    summary: str = Field(description="Closing summary in English (2-3 sentences).")  # 결론 요약


class TourPlanResult(BaseModel):
    """Final tour plan covering all days."""  # 전체 여행 플랜

    tour_plan: List[TourDayPlan] = Field(description="One plan per day.")  # 일자별 플랜 목록


# ──────────────────── LangGraph State ────────────────────


class TourPlannerGraphState(TypedDict):
    """Tour Planner v2 LangGraph 상태"""

    # 사용자 입력 (정규화)
    travel_days: int
    food_preference: FoodPreference
    days_input: List[TourDayInput]

    # 추가 장소 DB 조회 결과 (없으면 None)
    fixed_places: List[Optional[dict]]

    # 후보 장소 풀 (일자별, 그룹 균형 분배 후)
    candidate_places: List[List[dict]]

    # 최종
    tour_plan: TourPlanResult
