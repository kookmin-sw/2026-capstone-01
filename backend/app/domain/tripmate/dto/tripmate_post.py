from typing import List, Optional
from datetime import date, datetime
from dataclasses import dataclass

from app.domain.tripmate.model.tripmate_post import PreferredGender, CompanionType
from app.domain.auth.model.user_detail_inform import Gender


@dataclass
class PostAuthorData:
    """게시글 작성자 프로필 DTO"""
    user_name: str
    age: int
    gender: Gender
    nationality: str


@dataclass
class TripmatePostCreateData:
    """게시글 생성 응답 DTO (작성자 본인이므로 author 불필요)"""
    post_id: str
    user_id: str
    title: str
    content: str
    preferred_age_min: int
    preferred_age_max: int
    preferred_gender: PreferredGender
    region: str
    travel_start_date: date
    travel_end_date: date
    companion_type: CompanionType
    is_displayed: bool
    created_at: datetime
    updated_at: datetime
    image_urls: List[str]
    profile_image_url: Optional[str] = None


@dataclass
class TripmatePostData:
    """게시글 단건 응답 DTO"""
    post_id: str
    user_id: str
    author: PostAuthorData
    title: str
    content: str
    preferred_age_min: int
    preferred_age_max: int
    preferred_gender: PreferredGender
    region: str
    travel_start_date: date
    travel_end_date: date
    companion_type: CompanionType
    is_displayed: bool
    created_at: datetime
    updated_at: datetime
    like_count: int
    is_liked: bool
    image_urls: List[str]
    profile_image_url: Optional[str] = None


@dataclass
class TripmatePostListData:
    """게시글 목록 응답 DTO (커서 페이지네이션)"""
    posts: List[TripmatePostData]
    next_cursor: Optional[str]
