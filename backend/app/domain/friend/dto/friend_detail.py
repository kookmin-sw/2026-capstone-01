from typing import List, Optional
from dataclasses import dataclass

from app.domain.friend.model.friendship import FriendshipStatus
from app.domain.auth.model.user_travel_style import TravelStyle
from app.domain.auth.model.user_detail_inform import Gender


@dataclass
class FriendDetailData:
    """상대 유저 기본 프로필 + 내 기준 관계 상태 DTO.

    민감 정보(auth_provider, status, email, phone_number)는 포함하지 않는다.
    """

    # ── 공개 프로필 ──
    user_id: str
    user_name: str
    age: int
    gender: Gender
    nationality: str
    travel_styles: List[TravelStyle]

    # ── viewer 기준 관계 상태 ──
    friendship_id: Optional[str]            # 관계 row 가 존재할 때만 값
    friendship_status: Optional[FriendshipStatus]  # pending / accepted / rejected
    is_requester: Optional[bool]            # viewer 가 요청자인지. 관계 없으면 None
    i_blocked_peer: bool                    # 내가 상대를 차단했는가

    profile_image_url: Optional[str] = None
