"""피드 게시물 DTO.

- `FeedPostData` / `FeedPostListData` : service → router 응답 (SQLAlchemy 모델 격리).
- `FeedPostWithCounts`                 : repository → service row (post + 카운트 + viewer 좋아요).
"""
from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass

from app.domain.feed.model.feed_post import FeedPost, FeedVisibility


@dataclass(frozen=True)
class FeedPostWithCounts:
    """post + 카운트 합성 row. frozen=True 지만 내부 `post` 는 ORM 추적 mutable.

    `is_liked` 는 viewer 컨텍스트 종속 — viewer 미제공 호출 경로는 repository 가 SQL 측
    `false` 로 단락 평가.
    """
    post: FeedPost
    like_count: int
    comment_count: int
    is_liked: bool


@dataclass
class FeedPostData:
    """피드 게시물 단건 — 카운트는 응답 시점 스냅샷. 신규 업로드 직후는 모두 0."""
    post_id: str
    user_id: str
    visibility: FeedVisibility
    caption: Optional[str]
    original_url: str
    thumbnail_small_url: str
    thumbnail_medium_url: str
    like_count: int
    comment_count: int
    is_liked: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class FeedPostListData:
    posts: List[FeedPostData]
    next_cursor: Optional[str]
