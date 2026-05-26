"""사용자 인박스 (MongoDB).

설계:
- 단일 컬렉션 — feed/tripmate 좋아요·댓글 + 향후 친구·시스템 알림까지 `type` 으로 관리.
- denormalize snapshot — actor 닉네임/프로필 + target preview 를 insert 시점에 박는다.
  이후 닉네임이 바뀌어도 옛 항목은 옛 값 유지 (이벤트 기록), deep link 클릭 시 최신 데이터 fetch.
- soft hide (`display=False`) + 30일 TTL hard delete.
- `read_at` null = 미읽음 (뱃지 카운트 키).
- 본인→본인 항목 skip (service 가드). mute 는 푸시 전용, 인박스엔 영향 없음.
- fan-out 은 RDB 트랜잭션 *밖* best-effort insert (Mongo 일시 장애로 1건 누락돼도 응답 정상).

좋아요:
- 취소해도 항목 보존 (이벤트 기록).
- X 후 동일 행위 → 새 항목 OK (`uq_inbox_dedup` partial filter on `display=true`).
- X 안 누른 상태에서 취소→재좋아요 → unique 충돌 → service 가 멱등 skip (스팸 방지).

cascade (service 책임 — Mongo 는 auto 삭제 안 됨):
- 유저 탈퇴 → hard delete (recipient/actor 매칭).
- 게시글 삭제 → soft hide (`(target_type, target_id)`). 좋아요 취소 보존 정책과 비대칭이지만
  원본 소멸 시 deep link 404 가 확정이라 stale 알림 누적 방지.
- 댓글 단건 삭제는 cascade 안 함.
"""
from typing import Optional
from pymongo import IndexModel, ASCENDING, DESCENDING
from pydantic import Field
from enum import Enum
from datetime import datetime, timezone
from beanie import Document


INBOX_TTL_SECONDS = 60 * 60 * 24 * 30
COMMENT_PREVIEW_MAX_LENGTH = 100


class InboxItemType(str, Enum):
    """추가 시 `uq_inbox_dedup` 의미도 함께 검토 — 한 조합에 여러 개가 정상이면 별도 키 필요."""
    FEED_LIKE = "feed_like"
    FEED_COMMENT = "feed_comment"
    TRIPMATE_LIKE = "tripmate_like"


class TargetType(str, Enum):
    """deep link 라우팅 + cascade 정리 키."""
    FEED_POST = "feed_post"
    TRIPMATE_POST = "tripmate_post"


class InboxItem(Document):
    """actor 의 행위가 recipient 의 인박스에 쌓이는 항목."""

    recipient_id: str = Field(..., description="받는 유저 (게시물 owner)")
    actor_id: str = Field(..., description="행위자 (좋아요/댓글 누른 사람)")
    type: InboxItemType = Field(..., description="항목 종류")

    target_type: TargetType = Field(..., description="대상 리소스 타입")
    target_id: str = Field(..., description="대상 리소스 ID")
    comment_id: Optional[str] = Field(None, description="FEED_COMMENT 면 댓글 ID")

    # 항목 발생 시점 snapshot — 이후 변경되어도 갱신 안 함.
    actor_name: str = Field(..., description="actor 닉네임 (snapshot)")
    actor_profile_image_url: Optional[str] = Field(None, description="actor 프로필 (snapshot)")
    target_preview: Optional[str] = Field(None, description="피드 썸네일 URL 또는 tripmate title")
    comment_preview: Optional[str] = Field(
        None,
        description=f"댓글 본문 앞 {COMMENT_PREVIEW_MAX_LENGTH}자 (FEED_COMMENT 만)",
    )

    display: bool = Field(True, description="인박스 노출 여부. X 버튼 → False")
    read_at: Optional[datetime] = Field(None, description="null = 미읽음")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="생성 시각 (TTL 기준)",
    )

    class Settings:
        name = "inbox"
        indexes = [
            # 페이지네이션 핫패스. prefix `{recipient_id, display}` 가 미읽음 카운트도 커버.
            IndexModel(
                [("recipient_id", ASCENDING), ("display", ASCENDING), ("created_at", DESCENDING)],
                name="ix_inbox_recipient_display_created",
            ),
            # display=true 의 같은 조합 1건만 — partial filter 라 X 후 동일 행위는 새 항목 가능.
            # comment_id 가 LIKE 류엔 null → MongoDB unique 가 null 도 값 처리 → LIKE 는 자연스럽게 1건,
            # COMMENT 는 comment_id 마다 별도 항목.
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
            # 탈퇴 시 actor_id 매칭 정리용. recipient_id 는 위 인덱스 prefix 로 커버.
            # 게시글 삭제 cascade 는 `(target_type, target_id)` collection scan — 빈도 낮아 인덱스 미생성.
            IndexModel(
                [("actor_id", ASCENDING)],
                name="ix_inbox_actor",
            ),
            # 30일 후 hard delete — display=false 누적 방지.
            IndexModel(
                [("created_at", ASCENDING)],
                name="ttl_inbox_created",
                expireAfterSeconds=INBOX_TTL_SECONDS,
            ),
        ]
