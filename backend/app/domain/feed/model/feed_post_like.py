"""피드 게시물 좋아요.

- composite PK `(user_id, post_id)` 로 유저당 게시물 1회 제한 (DB-level).
- 양쪽 FK CASCADE — 유저 탈퇴 / 게시물 삭제 시 자동 정리.
- `ix_feed_post_like_post_id` — 게시물별 like_count / 누른 유저 목록 조회 최적화.
"""
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, DateTime, ForeignKey, Index

from app.database.session import Base


class FeedPostLike(Base):
    __tablename__ = "feed_post_like"

    user_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    post_id = Column(String(50), ForeignKey("feed_post.post_id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", backref="feed_post_likes")
    post = relationship("FeedPost", back_populates="likes")

    __table_args__ = (
        Index("ix_feed_post_like_post_id", "post_id"),
    )

    def __repr__(self):
        return f"<FeedPostLike(user_id={self.user_id}, post_id={self.post_id})>"
