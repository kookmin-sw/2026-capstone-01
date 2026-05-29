from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, Integer, ForeignKey, Index

from app.util.id_generator import generate_tripmate_image_id
from app.database.session import Base


class TripmatePostImage(Base):
    """여행 메이트 게시글 첨부 이미지"""
    __tablename__ = "tripmate_post_image"

    image_id = Column(String(50), primary_key=True, default=generate_tripmate_image_id)  # 이미지 고유 ID
    post_id = Column(String(50), ForeignKey("tripmate_post.post_id", ondelete="CASCADE"), nullable=False)  # 게시글 ID
    image_url = Column(String(500), nullable=False)  # 이미지 URL 경로
    image_order = Column(Integer, nullable=False, default=0)  # 이미지 정렬 순서

    post = relationship("TripmatePost", back_populates="images")

    __table_args__ = (
        Index("ix_tripmate_post_image_post_id", "post_id"),
    )

    def __repr__(self):
        return f"<TripmatePostImage(image_id={self.image_id}, post_id={self.post_id}, order={self.image_order})>"
