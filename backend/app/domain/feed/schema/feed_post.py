"""피드 게시물 Pydantic 스키마. multipart 업로드는 라우터의 `Form/File` 로 직접 처리."""
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from app.domain.feed.model.feed_post import FeedVisibility, CAPTION_MAX_LENGTH


# ──────────────────── Response ────────────────────

class FeedPostResponse(BaseModel):
    """피드 게시물 단건. 좋아요/댓글 카운트는 응답 시점 스냅샷."""
    post_id: str = Field(..., description="피드 게시물 고유 ID")
    user_id: str = Field(..., description="업로드한 유저 ID")
    visibility: FeedVisibility = Field(..., description="공개 범위 (private / friends / public)")
    caption: Optional[str] = Field(None, description="캡션 (없으면 null)")
    original_url: str = Field(..., description="원본 이미지 URL (한 변 최대 2048px)")
    thumbnail_small_url: str = Field(..., description="240×240 썸네일 URL — Feed grid 표시용")
    thumbnail_medium_url: str = Field(..., description="720×720 썸네일 URL — 확대/상세용")
    like_count: int = Field(..., description="좋아요 수 (응답 시점 스냅샷)")
    comment_count: int = Field(..., description="댓글 수 (응답 시점 스냅샷)")
    is_liked: bool = Field(..., description="viewer 가 좋아요 눌렀는지")
    created_at: datetime = Field(..., description="업로드 시각")
    updated_at: datetime = Field(..., description="마지막 수정 시각")


class FeedPostListResponse(BaseModel):
    """피드 게시물 목록 응답 (커서 페이지네이션)."""
    posts: List[FeedPostResponse] = Field(..., description="게시물 목록 (최신순)")
    next_cursor: Optional[str] = Field(
        None,
        description="다음 페이지 커서 (마지막 게시물의 post_id). 더 없으면 null.",
    )


# ──────────────────── Request ────────────────────

class UpdateVisibilityRequest(BaseModel):
    """공개 범위 변경 요청."""
    visibility: FeedVisibility = Field(..., description="새 공개 범위")


class UpdateCaptionRequest(BaseModel):
    """캡션 변경. null / 빈 / 공백만 → 캡션 삭제 (서비스가 None 정규화)."""
    caption: Optional[str] = Field(
        None,
        max_length=CAPTION_MAX_LENGTH,
        description=f"새 캡션 (최대 {CAPTION_MAX_LENGTH}자, null/빈/공백만 시 삭제)",
    )
