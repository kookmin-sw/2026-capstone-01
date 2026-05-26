from typing import List, Optional
from pydantic import BaseModel, Field

from app.domain.friend.model.friendship import FriendshipStatus
from app.domain.auth.model.user_travel_style import TravelStyle
from app.domain.auth.model.user_detail_inform import Gender


class FriendDetailResponse(BaseModel):
    # ── 공개 프로필 ──
    user_id: str = Field(..., description="상대 유저 고유 ID")
    user_name: str = Field(..., description="닉네임")
    age: int = Field(..., description="나이")
    gender: Gender = Field(..., description="성별 (male / female)")
    nationality: str = Field(..., description="국적 코드")
    travel_styles: List[TravelStyle] = Field(..., description="여행 스타일 목록")

    # ── viewer 기준 관계 상태 ──
    friendship_id: Optional[str] = Field(
        None, description="friendship row 고유 ID (관계가 없으면 null)"
    )
    friendship_status: Optional[FriendshipStatus] = Field(
        None, description="pending / accepted / rejected (관계가 없으면 null)"
    )
    is_requester: Optional[bool] = Field(
        None, description="현재 유저가 요청을 보낸 쪽인지 (관계가 없으면 null)"
    )
    i_blocked_peer: bool = Field(..., description="내가 상대를 차단했는지")
    profile_image_url: Optional[str] = Field(None, description="프로필 이미지 URL (없으면 null)")
