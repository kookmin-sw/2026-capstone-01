"""피드 게시물 좋아요 (PostgreSQL).

tripmate_post_like 패턴 그대로:
    - composite PK `(user_id, post_id)` 로 유저당 게시물 1회 제한 (DB-level 제약).
    - 양쪽 FK ON DELETE CASCADE — 유저 탈퇴 또는 게시물 삭제 시 자동 정리.
    - `ix_feed_post_like_post_id` 로 게시물별 좋아요 수 / 누른 유저 목록 조회 최적화.
"""
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, DateTime, ForeignKey, Index

from app.database.session import Base


class FeedPostLike(Base):
    """피드 게시물 좋아요 (유저당 게시물 1회 제한)."""
    __tablename__ = "feed_post_like"

    user_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)  # 좋아요 누른 유저 ID
    post_id = Column(String(50), ForeignKey("feed_post.post_id", ondelete="CASCADE"), primary_key=True)  # 대상 게시물 ID
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # 좋아요 누른 시각

    user = relationship("User", backref="feed_post_likes")
    post = relationship("FeedPost", back_populates="likes")

    __table_args__ = (
        Index("ix_feed_post_like_post_id", "post_id"),  # 게시물별 like_count / 좋아요 누른 유저 목록 조회용
    )

    def __repr__(self):
        return f"<FeedPostLike(user_id={self.user_id}, post_id={self.post_id})>"
