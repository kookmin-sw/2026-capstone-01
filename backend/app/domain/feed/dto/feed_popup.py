"""피드 팝업 DTO — 프로필 5종 + 최근 9개 피드.

popup 자체는 next_cursor 미제공 — 더보기는 클라가 `GET /feed/users/{user_id}` 로 분기.
"""
from typing import List, Optional
from dataclasses import dataclass

from app.domain.feed.dto.feed_post import FeedPostData
from app.domain.auth.model.user_travel_style import TravelStyle


# 인스타 popup 그리드 (3×3).
POPUP_FEED_LIMIT = 9


@dataclass
class FeedPopupData:
    user_id: str
    user_name: str
    nationality: str
    travel_styles: List[TravelStyle]
    profile_image_url: Optional[str]
    feed_items: List[FeedPostData]
