"""피드 좋아요 Pydantic 스키마."""
from typing import List, Optional
from pydantic import BaseModel, Field


class LikeResponse(BaseModel):
    """좋아요 추가/취소 응답."""
    post_id: str = Field(..., description="피드 게시물 고유 ID")
    like_count: int = Field(..., description="현재 좋아요 수")


class LikedUserItem(BaseModel):
    """좋아요 누른 유저 1명의 표시 정보."""
    user_id: str = Field(..., description="유저 고유 ID")
    user_name: str = Field(..., description="유저 닉네임 (detail 결손 시 빈 문자열)")
    profile_image_url: Optional[str] = Field(
        None, description="프로필 이미지 URL (없으면 null)",
    )


class LikedUsersResponse(BaseModel):
    """좋아요 누른 유저 목록 (최신순)."""
    post_id: str = Field(..., description="피드 게시물 고유 ID")
    users: List[LikedUserItem] = Field(
        ..., description="좋아요 누른 유저 목록 (최신순, 프로필 포함)",
    )
