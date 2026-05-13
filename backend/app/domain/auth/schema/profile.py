from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field

from app.domain.auth.model.user_travel_style import TravelStyle
from app.domain.auth.model.user_detail_inform import Gender


class ProfileUpdateRequest(BaseModel):
    """프로필 부분 수정 요청 — 변경할 필드만 포함.

    notification_muted / profile_image_url / status / auth_provider 는
    각각 별도 엔드포인트(알림 mute, 프로필 이미지 CRUD, 탈퇴, OAuth)에서 관리.

    travel_styles 의미:
        - 필드 미포함 또는 null → 변경 없음
        - [] (빈 배열)           → 기존 스타일 전체 삭제
        - [..]                   → 기존 스타일 전체 교체
    """

    email: Optional[EmailStr] = Field(
        None,
        description="이메일 주소",
        examples=["user@example.com"],
    )
    user_name: Optional[str] = Field(
        None,
        description="사용자 이름",
        examples=["조현상"],
    )
    phone_number: Optional[str] = Field(
        None,
        description="전화번호",
        examples=["010-1234-5678"],
    )
    age: Optional[int] = Field(
        None,
        description="나이",
        examples=[26],
    )
    gender: Optional[Gender] = Field(
        None,
        description="성별 (male / female)",
        examples=["male"],
    )
    nationality: Optional[str] = Field(
        None,
        description="국적",
        examples=["korea"],
    )
    travel_styles: Optional[List[TravelStyle]] = Field(
        None,
        description="여행 스타일 (전체 교체. [] = 전체 삭제, null/미포함 = 변경 없음)",
        examples=[["activity", "food_tour"]],
    )

    class Config:
        json_schema_extra = {
            "example": {
                "user_name": "홍길동",
                "age": 27,
                "travel_styles": ["activity", "foodie"],
            }
        }


class ProfileResponse(BaseModel):
    user_id: str = Field(
        ...,
        description="유저 고유 ID",
        examples=["USER_1712345678_abc12345"],
    )
    auth_provider: str = Field(
        ...,
        description="OAuth 제공자",
        examples=["google"],
    )
    status: str = Field(
        ...,
        description="유저 상태",
        examples=["active"],
    )
    email: str = Field(
        ...,
        description="이메일 주소",
        examples=["user@example.com"],
    )
    user_name: str = Field(
        ...,
        description="사용자 이름",
        examples=["조현상"],
    )
    phone_number: str = Field(
        ...,
        description="전화번호",
        examples=["010-1234-5678"],
    )
    age: int = Field(
        ...,
        description="나이",
        examples=[26],
    )
    gender: Gender = Field(
        ...,
        description="성별",
        examples=["male"],
    )
    nationality: str = Field(
        ...,
        description="국적",
        examples=["korea"],
    )
    travel_styles: List[TravelStyle] = Field(
        ...,
        description="여행 스타일 목록",
        examples=[["activity", "food_tour", "budget_moderate"]],
    )
    profile_image_url: Optional[str] = Field(
        None,
        description="프로필 이미지 URL (없으면 null)",
        examples=["https://cdn.example.com/profile/abc.jpg"],
    )
    notification_muted: bool = Field(
        ...,
        description="전역 알림 차단 여부 (true = 모든 푸시 차단)",
        examples=[False],
    )

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "USER_1712345678_abc12345",
                "auth_provider": "google",
                "status": "active",
                "email": "user@example.com",
                "user_name": "조현상",
                "phone_number": "010-1234-5678",
                "age": 26,
                "gender": "male",
                "nationality": "korea",
                "travel_styles": ["activity", "food_tour", "budget_moderate"],
                "profile_image_url": "https://cdn.example.com/profile/abc.jpg",
                "notification_muted": False,
            }
        }


class ProfileImageResponse(BaseModel):
    profile_image_url: str = Field(
        ...,
        description="저장된 프로필 이미지 URL",
        examples=["https://cdn.example.com/profile/abc.jpg"],
    )


class OtherUserProfileResponse(BaseModel):
    user_id: str = Field(
        ...,
        description="유저 고유 ID",
        examples=["USER_1712345678_abc12345"],
    )
    user_name: str = Field(
        ...,
        description="사용자 이름",
        examples=["조현상"],
    )
    nationality: str = Field(
        ...,
        description="국적",
        examples=["korea"],
    )
    travel_styles: List[TravelStyle] = Field(
        ...,
        description="여행 스타일 목록",
        examples=[["activity", "food_tour", "budget_moderate"]],
    )
    profile_image_url: Optional[str] = Field(
        None,
        description="프로필 이미지 URL (없으면 null)",
        examples=["https://cdn.example.com/profile/abc.jpg"],
    )


class OtherUserProfileListResponse(BaseModel):
    users: List[OtherUserProfileResponse] = Field(
        ...,
        description="본인을 제외한 ACTIVE 유저 목록 (최신 가입순)",
    )
