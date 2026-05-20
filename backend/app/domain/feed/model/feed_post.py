"""피드 게시물 메인 테이블 — 한 게시물 = 이미지 1장 + visibility + caption + (좋아요/댓글).

설계:
- URL 3종 (original / small / medium) 모두 NOT NULL — 동기 업로드 흐름이 partial 상태 보장.
- 유저 탈퇴 시 user_id FK CASCADE, 게시물 삭제 시 like/comment 도 cascade.
- storage prefix: `uploads/perm/{user_id}/feed/{post_id}/{variant}.{ext}`
  → 단건 삭제 = `delete_by_prefix` 한 호출로 변형 3종 일괄.
"""
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, Index
import enum

from app.util.id_generator import generate_feed_post_id
from app.database.session import Base


class FeedVisibility(str, enum.Enum):
    PRIVATE = "private"  # 본인만
    FRIENDS = "friends"  # ACCEPTED 친구 + 본인
    PUBLIC = "public"    # 차단 외 누구나


CAPTION_MAX_LENGTH = 100


class FeedPost(Base):
    """피드 게시물.

    `ix_feed_post_owner_visibility_created (user_id, visibility, created_at, post_id)`
    단일 컴파운드로 본인/친구/비친구 모든 페이지네이션 케이스 커버 — service 가 viewer 관계
    에 따라 `visibility IN (...)` 부분집합으로 좁히면 PG btree 가 reverse-scan 으로 처리.
    """
    __tablename__ = "feed_post"

    # server_default / onupdate 컬럼을 RETURNING 으로 즉시 ORM 반영 — async 의 lazy-load
    # (MissingGreenlet) 회피 표준 패턴.
    __mapper_args__ = {"eager_defaults": True}

    post_id = Column(String(50), primary_key=True, default=generate_feed_post_id)
    user_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    visibility = Column(
        Enum(FeedVisibility),
        nullable=False,
        default=FeedVisibility.PUBLIC,
    )
    caption = Column(String(CAPTION_MAX_LENGTH), nullable=True)

    # 동기 업로드 흐름이 partial 상태 차단 → 모두 NOT NULL.
    original_url = Column(String(500), nullable=False)         # 한 변 ≤ 2048px
    thumbnail_small_url = Column(String(500), nullable=False)  # 240×240 JPEG (grid)
    thumbnail_medium_url = Column(String(500), nullable=False) # 720×720 JPEG (확대)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="feed_posts")
    likes = relationship(
        "FeedPostLike", back_populates="post", cascade="all, delete-orphan",
    )
    comments = relationship(
        "FeedPostComment", back_populates="post", cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "ix_feed_post_owner_visibility_created",
            "user_id", "visibility", "created_at", "post_id",
        ),
    )

    def __repr__(self):
        return f"<FeedPost(post_id={self.post_id}, user_id={self.user_id}, visibility={self.visibility})>"
