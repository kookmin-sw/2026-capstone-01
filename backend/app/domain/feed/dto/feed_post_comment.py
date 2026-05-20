"""피드 댓글 DTO.

`FeedPostCommentData` 는 service → router 응답 (작성자 프로필 포함, joinedload 결과).
`CreateCommentResult` 는 service 내부 transfer — 트랜잭션이 응답 dto + fan-out 정보를
함께 합성하고 outer 가 분리해 사용.
"""
from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class FeedPostCommentData:
    """댓글 단건. detail 결손 시 user_name 빈 문자열 / profile_image_url None fallback."""
    comment_id: str
    post_id: str
    user_id: str
    user_name: str
    profile_image_url: Optional[str]
    content: str
    created_at: datetime
    updated_at: datetime


@dataclass
class FeedPostCommentListData:
    comments: List[FeedPostCommentData]
    next_cursor: Optional[str]


@dataclass
class CreateCommentResult:
    """`notify_recipient_id=None` 이면 본인→본인 댓글 — outer 가 fan-out skip."""
    dto: FeedPostCommentData
    notify_recipient_id: Optional[str]
    notify_post_preview: Optional[str]
