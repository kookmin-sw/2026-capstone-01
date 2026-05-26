from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass

from app.domain.friend.model.friendship import FriendshipStatus
from app.domain.auth.model.user_detail_inform import Gender


@dataclass
class FriendPeerData:
    """친구 관계의 상대방 프로필 DTO"""
    user_id: str
    user_name: str
    age: int
    gender: Gender
    nationality: str
    profile_image_url: Optional[str] = None


@dataclass
class FriendshipData:
    """친구 관계 응답 DTO (상대 프로필 포함)"""
    friendship_id: str
    status: FriendshipStatus
    peer: FriendPeerData
    is_requester: bool  # 현재 조회 유저가 요청자인지 여부
    created_at: datetime
    updated_at: datetime


@dataclass
class FriendshipListData:
    """친구/요청/차단 목록 응답 DTO (커서 페이지네이션)"""
    items: List[FriendshipData]
    next_cursor: Optional[str]
