from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime

from app.domain.friend.model.friendship import FriendshipStatus
from app.domain.auth.model.user_detail_inform import Gender


# ──────────────────── Request ────────────────────

class SendFriendRequestBody(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "addressee_id": "USER_1700000000_abcdef12",
            }
        }
    )

    addressee_id: str = Field(..., description="친구 요청을 받을 유저 ID")


# ──────────────────── Response ────────────────────

class FriendPeerResponse(BaseModel):
    user_id: str = Field(..., description="상대 유저 ID")
    user_name: str = Field(..., description="상대 닉네임")
    age: int = Field(..., description="상대 나이")
    gender: Gender = Field(..., description="상대 성별 (male / female)")
    nationality: str = Field(..., description="상대 국적")
    profile_image_url: Optional[str] = Field(None, description="프로필 이미지 URL (없으면 null)")


class FriendshipResponse(BaseModel):
    friendship_id: str = Field(..., description="친구 관계 고유 ID")
    status: FriendshipStatus = Field(..., description="관계 상태 (pending / accepted / rejected)")
    peer: FriendPeerResponse = Field(..., description="상대 유저 프로필")
    is_requester: bool = Field(..., description="현재 유저가 요청자인지 여부")
    created_at: datetime = Field(..., description="생성 시각")
    updated_at: datetime = Field(..., description="마지막 변경 시각")


class FriendshipListResponse(BaseModel):
    items: List[FriendshipResponse] = Field(..., description="친구/요청/차단 목록")
    next_cursor: Optional[str] = Field(None, description="다음 페이지 커서 (마지막 페이지면 null)")
