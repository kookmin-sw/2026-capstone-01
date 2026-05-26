"""피드 좋아요 DTO.

`LikedUserData` 는 service → router 응답 (joinedload 결과).
`AddLikePayload` 는 service 내부 transfer — `recipient_id == actor_id` 면 outer 가 fan-out
skip 하므로 snapshot 필드는 더미 값.
"""
from typing import Optional
from dataclasses import dataclass


@dataclass
class LikedUserData:
    """detail 결손 시 user_name 빈 문자열 / profile_image_url None fallback."""
    user_id: str
    user_name: str
    profile_image_url: Optional[str]


@dataclass
class AddLikePayload:
    like_count: int
    recipient_id: str
    actor_name: str
    actor_profile_image_url: Optional[str]
    post_preview: Optional[str]
