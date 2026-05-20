"""인박스 DTO. `read_at` → `is_read` 평탄화 (정확한 read 시각은 클라가 거의 안 씀)."""
from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass

from app.domain.notification.model.inbox import InboxItemType, TargetType


@dataclass
class InboxItemData:
    """단건 응답. snapshot 필드는 항목 발생 시점 값 — 최신 데이터는 deep link 클릭 시 별도 fetch."""
    inbox_item_id: str
    type: InboxItemType
    actor_id: str
    actor_name: str
    actor_profile_image_url: Optional[str]
    target_type: TargetType
    target_id: str
    comment_id: Optional[str]
    target_preview: Optional[str]
    comment_preview: Optional[str]
    is_read: bool
    created_at: datetime


@dataclass
class InboxListData:
    """커서 페이지네이션. `next_cursor` 는 마지막 항목의 ISO created_at, 더 없으면 None."""
    items: List[InboxItemData]
    next_cursor: Optional[str]
