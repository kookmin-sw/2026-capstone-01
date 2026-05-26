from sqlalchemy.sql import func
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint, Index

from app.util.id_generator import generate_favorite_place_id
from app.database.session import Base


class FavoritePlace(Base):
    """유저 즐겨찾기 장소 (RDB)

    - User(RDB)와 Place(MongoDB) 간의 즐겨찾기 관계
    - place_id는 MongoDB Place 컬렉션의 Google Places ID를 참조 (FK 제약 없음)
    """

    __tablename__ = "favorite_place"

    favorite_id = Column(String(50), primary_key=True, default=generate_favorite_place_id)
    user_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    place_id = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "place_id", name="uq_user_favorite_place"),
        Index("ix_favorite_user_id", "user_id"),
        Index("ix_favorite_place_id", "place_id"),
    )

    def __repr__(self):
        return f"<FavoritePlace(favorite_id={self.favorite_id}, user_id={self.user_id}, place_id={self.place_id})>"
