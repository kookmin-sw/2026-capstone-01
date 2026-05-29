from typing import List, Optional
from dataclasses import dataclass

from app.domain.auth.model.user_travel_style import TravelStyle
from app.domain.auth.model.user_detail_inform import Gender
from app.domain.auth.model.user import UserStatus
from app.config.oauth import OAuthProvider


@dataclass
class ProfileData:
    user_id: str
    auth_provider: OAuthProvider
    status: UserStatus
    email: str
    user_name: str
    phone_number: str
    age: int
    gender: Gender
    nationality: str
    travel_styles: List[TravelStyle]
    profile_image_url: Optional[str] = None
    notification_muted: bool = False


@dataclass
class ProfileImageData:
    """프로필 이미지 추가/수정 결과 DTO"""
    profile_image_url: str


@dataclass
class OtherUserProfileData:
    """탐색 목록용 타 유저 프로필 DTO — 최소 공개 정보만."""
    user_id: str
    user_name: str
    nationality: str
    travel_styles: List[TravelStyle]
    profile_image_url: Optional[str] = None


@dataclass
class ProfileStatsData:
    """마이페이지 통계 DTO — 본인 활동 합계.

    응답 시점 스냅샷. 좋아요/친구 카운트는 cross-domain 집계 (feed + friend) 이지만
    응답이 단일 평면 객체라 클라이언트 매핑이 단순. 
    미래에 `total_feed_posts` 같은 필드가 추가될 가능성을 염두에 둔 확장 친화 구조.
    """
    total_feed_likes: int
    total_friends: int
