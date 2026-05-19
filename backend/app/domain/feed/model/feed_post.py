"""피드 게시물 메인 테이블 (PostgreSQL).

기획안의 인스타그램 형 마이페이지 Feed 탭 — 유저별 게시물 갤러리.
한 게시물 = 이미지 1장 + visibility + caption + (좋아요/댓글).

설계 결정:
    - tripmate (post / post_image / post_like) 패턴을 차용한 RDB 모델. 좋아요/댓글이
      추가되면서 (post, user) 다대다 + (post 1:N user) 관계 표현이 RDB 에서 자연스럽다.
    - URL 3종 (original / small / medium) 모두 NOT NULL — 동기 업로드 (Pillow 처리 + S3 3건
      + INSERT) 가 한 트랜잭션이라 partial 상태가 DB 에 들어가지 않는다.
    - cascade: `user_id` FK ON DELETE CASCADE 로 탈퇴 시 자동 정리. 게시물 삭제 시
      `feed_post_like` / `feed_post_comment` 도 cascade 로 일괄 제거 (관계 cascade).
    - storage prefix: `uploads/perm/{user_id}/feed/{post_id}/{variant}.{ext}` — 단건 삭제
      = `delete_by_prefix({user_id}/feed/{post_id})` 한 호출로 변형 3종 모두 정리.
"""
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, Index
import enum

from app.util.id_generator import generate_feed_post_id
from app.database.session import Base


class FeedVisibility(str, enum.Enum):
    """피드 게시물 공개 범위.

    PRIVATE : 본인만 조회 가능
    FRIENDS : ACCEPTED 친구 + 본인 조회 가능
    PUBLIC  : 차단 관계 외 누구나 조회 가능
    """
    PRIVATE = "private"
    FRIENDS = "friends"
    PUBLIC = "public"


# caption 한도
CAPTION_MAX_LENGTH = 100


class FeedPost(Base):
    """피드 게시물 메타데이터.

    인덱스 설계:
        `ix_feed_post_owner_visibility_created (user_id, visibility, created_at, post_id)`
        단일 컴파운드로 본인 / 친구 / 비친구 모든 페이지네이션 케이스 커버.
        service 가 viewer 관계에 따라 `visibility ∈ {private, friends, public}` 부분집합을
        `IN` 으로 좁히며, PG btree 가 `IN (...)` + `ORDER BY ... DESC` 양쪽을 reverse-scan
        으로 처리한다.
    """
    __tablename__ = "feed_post"

    # `eager_defaults=True` — server_default / onupdate 컬럼 (`updated_at = func.now()`) 을
    # INSERT/UPDATE 의 RETURNING 절로 즉시 ORM 에 반영. 미적용 시 onupdate 컬럼이 stale
    # 마킹 → `_to_dto` 등 후속 access 가 lazy-load 발동 → async 경계에서 MissingGreenlet.
    # SQLAlchemy 2.x async 환경에서 server-eval 컬럼을 안전하게 다루는 표준 패턴.
    __mapper_args__ = {"eager_defaults": True}

    post_id = Column(String(50), primary_key=True, default=generate_feed_post_id)  # 피드 게시물 고유 ID
    user_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)  # 업로드한 유저 ID
    visibility = Column(
        Enum(FeedVisibility),
        nullable=False,
        default=FeedVisibility.PUBLIC,
    )  # 공개 범위 (private / friends / public)
    caption = Column(String(CAPTION_MAX_LENGTH), nullable=True)  # 게시물 캡션 (최대 100자)

    # ── 다해상도 URL — 모두 NOT NULL. 동기 업로드 흐름이 보장.
    original_url = Column(String(500), nullable=False)         # 원본 (한 변 ≤ 2048px)
    thumbnail_small_url = Column(String(500), nullable=False)  # 240×240 JPEG (Feed grid)
    thumbnail_medium_url = Column(String(500), nullable=False) # 720×720 JPEG (확대/상세)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # 업로드 시각
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())  # 마지막 수정 시각

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
