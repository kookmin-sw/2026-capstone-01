from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, DateTime, ForeignKey, Index

from app.database.session import Base


class TripmatePostLike(Base):
    """여행 메이트 게시글 좋아요 (유저당 게시글 1회 제한)"""
    __tablename__ = "tripmate_post_like"

    user_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)  # 좋아요 누른 유저 ID
    post_id = Column(String(50), ForeignKey("tripmate_post.post_id", ondelete="CASCADE"), primary_key=True)  # 좋아요 대상 게시글 ID
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # 좋아요 누른 시각

    user = relationship("User", backref="tripmate_post_likes")
    post = relationship("TripmatePost", back_populates="likes")

    __table_args__ = (
        Index("ix_tripmate_post_like_post_id", "post_id"),  # 게시글별 좋아요 목록 조회용
    )

    def __repr__(self):
        return f"<TripmatePostLike(user_id={self.user_id}, post_id={self.post_id})>"
