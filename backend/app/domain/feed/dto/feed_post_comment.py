"""피드 댓글 DTO — 서비스 → 라우터 경계 + 서비스 내부 transfer.

서비스가 SQLAlchemy 모델 직접 노출 대신 DTO 변환. DB 스키마 변경이 API 계약을 깨지 않게 분리.
작성자 프로필 (`user_name` / `profile_image_url`) 은 repository 의 `joinedload` 로 단일
JOIN 쿼리에 함께 로드되어 DTO 에 포함 — 클라이언트가 별도 batch 조회 없이 즉시 표시.

`CreateCommentResult` 는 service 내부 transfer 객체 — 트랜잭션 (`_create_comment_tx`) 이
응답 dto + fan-out 정보를 함께 합성하고 outer (`create_comment`) 가 분리해서 사용.
"""
from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class FeedPostCommentData:
    """댓글 단건 응답 DTO — 작성자 프로필 정보 포함.

    `user_name` 은 `user_detail_inform.user_name` 매핑. detail 결손 (회원가입 미완료 등
    비정상 상태) 시 빈 문자열 fallback (chat / like 도메인 컨벤션 일치).
    `profile_image_url` 도 동일 None fallback.
    """
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
    """댓글 목록 응답 DTO (커서 페이지네이션, 최신순)."""
    comments: List[FeedPostCommentData]
    next_cursor: Optional[str]


@dataclass
class CreateCommentResult:
    """댓글 작성 service 내부 transfer.

    트랜잭션 안에서 응답 dto + fan-out 필요 정보를 한 번에 합성. router 에는 `dto` 만
    노출, `notify_*` 필드는 outer 가 InboxService 로 전달. `notify_recipient_id`
    가 None 이면 본인→본인 댓글 — outer 가 fan-out skip.
    """
    dto: FeedPostCommentData
    notify_recipient_id: Optional[str]
    notify_post_preview: Optional[str]
