from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint, Index

from app.util.id_generator import generate_fcm_token_id
from app.database.session import Base


class FcmToken(Base):
    """FCM 디바이스 토큰 — 한 유저 1:N 디바이스.

    - `token` UNIQUE — 디바이스 식별자. 동일 토큰 재등록 시 서비스가 owner 만 교체.
    - 탈퇴 시 users FK CASCADE.
    - UNREGISTERED/INVALID 응답이면 서비스가 즉시 DELETE (만료 토큰 누적 방지).
    """

    __tablename__ = "fcm_token"
    # server-eval `updated_at` RETURNING 반영 — async lazy-load 회피.
    __mapper_args__ = {"eager_defaults": True}

    fcm_token_id = Column(String(50), primary_key=True, default=generate_fcm_token_id)
    user_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    token = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="fcm_tokens")

    __table_args__ = (
        UniqueConstraint("token", name="uq_fcm_token_token"),
        Index("ix_fcm_token_user_id", "user_id"),
    )

    def __repr__(self):
        return f"<FcmToken(fcm_token_id={self.fcm_token_id}, user_id={self.user_id}, token={self.token[:16]}...)>"
