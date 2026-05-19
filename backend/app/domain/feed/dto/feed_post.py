"""피드 게시물 DTO — 두 경계의 데이터 전송 객체.

본 모듈에는 두 종류의 dataclass 가 모인다:

1. **응답 DTO** (service → router) — `FeedPostData`, `FeedPostListData`
   서비스가 SQLAlchemy 모델 (`FeedPost`) 을 직접 라우터로 흘리지 않고 본 DTO 로 변환해
   노출. DB 스키마 변경이 API 계약을 깨지 않게 격리.

2. **Row DTO** (repository → service) — `FeedPostWithCounts`
   repository 가 단일 SELECT 의 correlated subquery 로 합성한 결과 (ORM 모델 + 좋아요/
   댓글 카운트). ORM 모델 그대로는 카운트를 표현 못 해 별도 row 타입이 필요. service 가
   `.post` unwrap 또는 카운트까지 사용 후 응답 DTO 로 재변환.
"""
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime

from app.domain.feed.model.feed_post import FeedPost, FeedVisibility


@dataclass(frozen=True)
class FeedPostWithCounts:
    """FeedPost + 좋아요/댓글 수 + viewer 좋아요 여부 합성 row — repository → service.

    repository 가 단일 SELECT (correlated subquery 3개) 로 한 번에 로드 → service 가
    `.post` 로 unwrap 하거나 (`access.load_viewable_post` 처럼) 카운트까지 사용 (`_to_dto`).
    frozen=True 로 row 자체는 불변, 내부의 SQLAlchemy `post` 객체는 ORM 추적되는 mutable
    상태 그대로 유지 (visibility/caption 수정 경로에서 직접 mutate 가능).

    `is_liked` 는 viewer 컨텍스트에 종속 — 같은 게시물도 viewer 마다 값이 다르다. viewer
    가 결정되지 않는 호출 경로는 repository 가 SQL 측 `false` 로 단락 평가.
    """
    post: FeedPost
    like_count: int
    comment_count: int
    is_liked: bool


@dataclass
class FeedPostData:
    """피드 게시물 단건 응답 DTO — 좋아요/댓글 카운트 + viewer 좋아요 여부 포함.

    카운트 값은 응답 시점의 스냅샷. 클라이언트가 좋아요/댓글 액션 후 게시물 상세를 다시
    조회하면 갱신된 값. 신규 업로드 직후는 항상 0, `is_liked` 는 항상 False.
    """
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
    """피드 게시물 목록 응답 DTO (커서 페이지네이션)."""
    posts: List[FeedPostData]
    next_cursor: Optional[str]
