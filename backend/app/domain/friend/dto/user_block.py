from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass

from app.domain.friend.dto.friendship import FriendPeerData


@dataclass
class UserBlockData:
    """차단 관계 응답 DTO (차단 대상 프로필 포함)"""
    block_id: str
    blocked: FriendPeerData
    created_at: datetime


@dataclass
class UserBlockListData:
    """내가 차단한 유저 목록 응답 DTO (커서 페이지네이션)"""
    items: List[UserBlockData]
    next_cursor: Optional[str]
