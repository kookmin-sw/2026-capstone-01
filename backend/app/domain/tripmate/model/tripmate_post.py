from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, Integer, Date, DateTime, Enum, Boolean, ForeignKey, Index, CheckConstraint
import enum

from app.util.id_generator import generate_tripmate_post_id
from app.database.session import Base


class PreferredGender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    ANY = "any"


class CompanionType(str, enum.Enum):
    FRIEND = "friend"
    FAMILY = "family"
    COUPLE = "couple"
    SOLE = "sole"


class TripmatePost(Base):
    """여행 메이트 모집 게시글"""
    __tablename__ = "tripmate_post"
    # `eager_defaults=True` — server-eval `updated_at` 을 RETURNING 으로 즉시 ORM 반영.
    # async 환경에서 lazy-load (MissingGreenlet) 회피 표준 패턴.
    __mapper_args__ = {"eager_defaults": True}

    post_id = Column(String(50), primary_key=True, default=generate_tripmate_post_id)  # 게시글 고유 ID
    user_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)  # 작성자 ID
    title = Column(String(100), nullable=False)  # 게시글 제목
    content = Column(String(500), nullable=False)  # 게시글 내용 (10자 ~ 500자)
    preferred_age_min = Column(Integer, nullable=False)  # 선호 나이 하한
    preferred_age_max = Column(Integer, nullable=False)  # 선호 나이 상한
    preferred_gender = Column(Enum(PreferredGender), nullable=False)  # 선호 성별 (male, female, any)
    region = Column(String(100), nullable=False)  # 여행 지역
    travel_start_date = Column(Date, nullable=False)  # 여행 시작일
    travel_end_date = Column(Date, nullable=False)  # 여행 종료일
    companion_type = Column(Enum(CompanionType), nullable=False)  # 선호 동행 타입 (friend, family, couple, sole)
    is_displayed = Column(Boolean, nullable=False, default=True)  # 게시글 표시 여부
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # 게시글 작성일
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())  # 게시글 수정일

    user = relationship("User", backref="tripmate_posts")
    images = relationship("TripmatePostImage", back_populates="post", cascade="all, delete-orphan")
    likes = relationship("TripmatePostLike", back_populates="post", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_tripmate_post_user_id", "user_id"),
        Index("ix_tripmate_post_region", "region"),
        Index("ix_tripmate_post_travel_dates", "travel_start_date", "travel_end_date"),
        CheckConstraint("preferred_age_min <= preferred_age_max", name="ck_preferred_age_range"),
        CheckConstraint("travel_start_date <= travel_end_date", name="ck_travel_date_range"),
        CheckConstraint("char_length(content) >= 10", name="ck_content_min_length"),
    )

    def __repr__(self):
        return f"<TripmatePost(post_id={self.post_id}, user_id={self.user_id}, title={self.title})>"
