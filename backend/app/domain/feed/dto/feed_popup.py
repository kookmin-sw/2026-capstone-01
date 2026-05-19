"""피드 팝업 DTO — 다른 유저 프로필 미리보기 합성 응답.

`GET /feed/popup/{user_id}` 의 service → router 경계 표현.

구성:
    - 타 유저 프로필 5종 (user_id, user_name, nationality, travel_styles, profile_image_url)
      = `auth.OtherUserProfileResponse` 와 동일 필드 (필드 복제는 도메인 자율성 우선,
      auth schema 변경 시 두 곳 갱신 부담 감수).
    - 첫 페이지 피드 (최근 9개) — `FeedPostData` 그대로 재사용. 더보기는 클라이언트가
      일반 `GET /feed/users/{user_id}` 로 분기 (인스타 popup 패턴).
"""
from typing import List, Optional
from dataclasses import dataclass

from app.domain.feed.dto.feed_post import FeedPostData
from app.domain.auth.model.user_travel_style import TravelStyle


# popup 의 feed item 개수 — 인스타 popup 의 그리드 (3×3) 와 동일.
POPUP_FEED_LIMIT = 9


@dataclass
class FeedPopupData:
    """팝업 응답 DTO — 프로필 5종 + 최근 피드 9개."""
    user_id: str
    user_name: str
    nationality: str
    travel_styles: List[TravelStyle]
    profile_image_url: Optional[str]
    feed_items: List[FeedPostData]
