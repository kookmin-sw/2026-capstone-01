"""피드 게시물 댓글.

- 양쪽 FK CASCADE — 유저 탈퇴 / 게시물 삭제 시 자동 정리.
- `ix_feed_post_comment_post_created` — 게시물별 시간순 페이지네이션.
- `ck_feed_post_comment_min_length` — 빈 본문 DB-level 방어선.
"""
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, CheckConstraint

from app.util.id_generator import generate_feed_post_comment_id
from app.database.session import Base


COMMENT_MAX_LENGTH = 500


class FeedPostComment(Base):
    __tablename__ = "feed_post_comment"

    # server-eval `updated_at` RETURNING 반영 → lazy-load 회피.
    __mapper_args__ = {"eager_defaults": True}

    comment_id = Column(String(50), primary_key=True, default=generate_feed_post_comment_id)
    post_id = Column(String(50), ForeignKey("feed_post.post_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    content = Column(String(COMMENT_MAX_LENGTH), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="feed_post_comments")
    post = relationship("FeedPost", back_populates="comments")

    __table_args__ = (
        Index("ix_feed_post_comment_post_created", "post_id", "created_at"),
        CheckConstraint("char_length(content) >= 1", name="ck_feed_post_comment_min_length"),
    )

    def __repr__(self):
        return f"<FeedPostComment(comment_id={self.comment_id}, post_id={self.post_id}, user_id={self.user_id})>"
