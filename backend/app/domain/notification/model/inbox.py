"""사용자 인박스 (MongoDB).

설계 정책 — 합의 사항:
    - **단일 컬렉션** — feed/tripmate 좋아요·댓글 + 향후 친구·시스템 알림까지 `type` 필드 하나로 관리.
      인박스는 한 유저의 시간순 timeline 이라 컬렉션 분리는 페이지네이션 비용 ↑.
    - **denormalize snapshot** — actor 닉네임/프로필 이미지, target preview 를 insert 시점에 박아 둔다.
      인박스 조회 시 RDB JOIN 회피. 이후 닉네임이 바뀌어도 옛 항목은 옛 닉네임으로 남음 (이벤트 발생
      시점의 사실 기록). deep link 클릭 시점에 RDB 에서 진짜 최신 데이터를 다시 fetch.
    - **soft hide** — X 버튼 → `display=False`. 30일 TTL 로 hard delete (자동).
    - **read_at** — 미읽음 뱃지 (`display=true AND read_at=null` count) 용. null 이면 미읽음.
    - **본인→본인 항목 skip** — service 레이어에서 `recipient_id == actor_id` 가드.
    - **mute 분리** — 푸시(FCM) 는 mute 가드 적용 / 인박스는 영향 없음.
    - **fan-out 시점** — RDB 트랜잭션 커밋 *후* best-effort insert. Mongo 일시 장애로 항목 1건이
      누락되어도 사용자 응답은 정상 (try/except + 로그). outbox 패턴은 Phase 2.

좋아요 정책:
    - 좋아요 취소해도 항목 그대로 (이벤트 발생 사실의 기록).
    - X 로 숨긴 후 같은 사람이 다시 좋아요 → 새 항목 OK (`uq_inbox_dedup` partial filter).
    - X 안 누른 상태에서 좋아요 취소→재좋아요 → unique 충돌 → service 가 `DuplicateKeyError` catch & skip (멱등). 스팸 방지.

cascade 정리 (service 레이어 책임 — Mongo 는 자동 삭제되지 않음):
    - 유저 탈퇴 → `delete_many({$or:[{recipient_id:u},{actor_id:u}]})` (hard delete)
    - 게시글 삭제 → `update_many({target_type, target_id}, {display:false})` (soft hide).
      좋아요 취소 항목 보존 정책과는 비대칭 — 원본 게시글이 사라진 알림은 deep link 404
      가 확정이라 인박스에 남길 가치 없음. 댓글 단건 삭제는 cascade 안 함.

문서 라이프사이클:
    INSERT (RDB 커밋 후, best-effort) → display 토글 / read_at 갱신 → 30일 TTL hard delete
"""
from typing import Optional
from pymongo import IndexModel, ASCENDING, DESCENDING
from pydantic import Field
from enum import Enum
from datetime import datetime, timezone
from beanie import Document


# 30일 TTL (초 단위) — `created_at` 기준 expireAfterSeconds 로 hard delete
INBOX_TTL_SECONDS = 60 * 60 * 24 * 30

# 댓글 미리보기 길이 — 인박스 표시용 snapshot
COMMENT_PREVIEW_MAX_LENGTH = 100


class InboxItemType(str, Enum):
    """인박스 항목 종류. MongoDB 에는 value(snake_case) 로 저장된다.

    추가 시 `uq_inbox_dedup` 의미를 함께 검토 — comment 류처럼
    한 (recipient, actor, target) 조합에 여러 개가 정상이면 별도 키 필요.
    """
    FEED_LIKE = "feed_like"
    FEED_COMMENT = "feed_comment"
    TRIPMATE_LIKE = "tripmate_like"


class TargetType(str, Enum):
    """항목 대상 리소스 타입 — deep link 라우팅 + cascade 정리 키."""
    FEED_POST = "feed_post"
    TRIPMATE_POST = "tripmate_post"


class InboxItem(Document):
    """사용자 활동 인박스 항목 — actor 의 행위가 recipient 의 인박스에 쌓인다."""

    # ──────────────────── 라우팅 ────────────────────
    recipient_id: str = Field(..., description="항목 받는 유저 ID (게시물 owner)")
    actor_id: str = Field(..., description="행위자 유저 ID (좋아요/댓글 누른 사람)")
    type: InboxItemType = Field(..., description="항목 종류")

    # ──────────────────── 대상 (deep link / cascade) ────────────────────
    target_type: TargetType = Field(..., description="대상 리소스 타입")
    target_id: str = Field(..., description="대상 리소스 ID (feed_post.post_id 등)")
    comment_id: Optional[str] = Field(
        None,
        description="FEED_COMMENT 인 경우 댓글 ID",
    )

    # ──────────────────── 표시용 snapshot (denormalize) ────────────────────
    # 항목 발생 시점에 박아 두는 값 — 이후 변경되어도 갱신 안 함.
    # deep link 클릭 시 진짜 최신 데이터를 RDB 에서 fetch.
    actor_name: str = Field(..., description="항목 시점의 actor 닉네임")
    actor_profile_image_url: Optional[str] = Field(None, description="항목 시점의 actor 프로필 이미지")
    target_preview: Optional[str] = Field(None, description="피드 썸네일 URL 또는 tripmate title")
    comment_preview: Optional[str] = Field(
        None,
        description=f"댓글 본문 앞 {COMMENT_PREVIEW_MAX_LENGTH}자 (FEED_COMMENT 만)",
    )

    # ──────────────────── 상태 ────────────────────
    display: bool = Field(True, description="인박스 노출 여부. X 버튼 → False")
    read_at: Optional[datetime] = Field(None, description="읽음 시각. null = 미읽음 (뱃지 카운트 키)")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="항목 생성 시각 (TTL 기준)",
    )

    class Settings:
        name = "inbox"
        indexes = [
            # 인박스 페이지네이션 핫패스. prefix `{recipient_id, display}` 로
            # 미읽음 뱃지 카운트 (`read_at=null` 추가 필터) 도 함께 커버.
            IndexModel(
                [("recipient_id", ASCENDING), ("display", ASCENDING), ("created_at", DESCENDING)],
                name="ix_inbox_recipient_display_created",
            ),
            # display=true 인 같은 (recipient, actor, type, target, comment) 조합 1건만 — 중복 항목 방지.
            # partial filter 라 X 로 숨긴(display=false) 후 같은 행위 반복 시 새 항목 가능.
            # comment_id 가 LIKE 류엔 null 이지만 MongoDB unique 는 null 도 값으로 처리 →
            # LIKE 는 자연스럽게 1건, COMMENT 는 comment_id 마다 별도 항목.
            IndexModel(
                [
                    ("recipient_id", ASCENDING),
                    ("actor_id", ASCENDING),
                    ("type", ASCENDING),
                    ("target_id", ASCENDING),
                    ("comment_id", ASCENDING),
                ],
                name="uq_inbox_dedup",
                unique=True,
                partialFilterExpression={"display": True},
            ),
            # 탈퇴 시 actor_id 매칭 정리. recipient_id 는 위 compound 인덱스 prefix 로 커버.
            # 게시글 삭제 cascade (`hide_by_target`) 는 `(target_type, target_id)` 매칭 —
            # 별도 인덱스 없이 collection scan. 게시글 삭제 빈도가 낮고 best-effort 호출이라
            # 인박스 컬렉션 크기 임계치 넘으면 인덱스 추가 검토.
            IndexModel(
                [("actor_id", ASCENDING)],
                name="ix_inbox_actor",
            ),
            # 30일 후 자동 hard delete — display=false 누적 방지.
            IndexModel(
                [("created_at", ASCENDING)],
                name="ttl_inbox_created",
                expireAfterSeconds=INBOX_TTL_SECONDS,
            ),
        ]
