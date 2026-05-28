"""인박스 Pydantic 스키마."""
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from app.domain.notification.model.inbox import InboxItemType, TargetType


class InboxItemResponse(BaseModel):
    """인박스 단건. snapshot 필드는 항목 발생 시점 값 — 최신 데이터는 deep link 클릭 시 별도 fetch."""
    inbox_item_id: str = Field(..., description="Mongo ObjectId hex string")
    type: InboxItemType = Field(..., description="항목 종류")
    actor_id: str = Field(..., description="행위자 user_id")
    actor_name: str = Field(..., description="행위자 닉네임 (snapshot)")
    actor_profile_image_url: Optional[str] = Field(None, description="행위자 프로필 URL (snapshot)")
    target_type: TargetType = Field(..., description="대상 리소스 타입 (deep link 분기)")
    target_id: str = Field(..., description="대상 리소스 ID")
    comment_id: Optional[str] = Field(None, description="FEED_COMMENT 면 댓글 ID (deep link 앵커)")
    target_preview: Optional[str] = Field(None, description="피드 썸네일 URL 또는 tripmate title (snapshot)")
    comment_preview: Optional[str] = Field(None, description="댓글 본문 미리보기 (FEED_COMMENT 만)")
    is_read: bool = Field(..., description="읽음 여부")
    created_at: datetime = Field(..., description="생성 시각")


class InboxListResponse(BaseModel):
    items: List[InboxItemResponse] = Field(..., description="인박스 항목 (최신순)")
    next_cursor: Optional[str] = Field(
        None,
        description="다음 페이지 커서 (마지막 항목의 created_at ISO string). 더 없으면 null.",
    )


class UnreadCountResponse(BaseModel):
    unread_count: int = Field(..., ge=0, description="미읽음 수 (999+ 캡)")
