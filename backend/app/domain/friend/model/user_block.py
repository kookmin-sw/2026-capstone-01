from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint, Index, CheckConstraint

from app.util.id_generator import generate_user_block_id
from app.database.session import Base


class UserBlock(Base):
    """유저 차단 관계 (단방향)

    - blocker_id: 차단한 유저
    - blocked_id: 차단당한 유저
    - (blocker_id, blocked_id) 유일 — 같은 대상을 두 번 차단 불가
    - 양방향 차단(상호 차단)은 서로 다른 row 2개로 공존 가능
    - 자기 자신 차단 불가 (CheckConstraint)
    """

    __tablename__ = "user_block"

    block_id = Column(String(50), primary_key=True, default=generate_user_block_id)
    blocker_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)  # 차단한 유저
    blocked_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)  # 차단당한 유저
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    blocker = relationship("User", foreign_keys=[blocker_id], backref="user_blocks_made")
    blocked = relationship("User", foreign_keys=[blocked_id], backref="user_blocks_received")

    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_user_block_pair"),
        Index("ix_user_block_blocker", "blocker_id"),
        Index("ix_user_block_blocked", "blocked_id"),
        CheckConstraint("blocker_id <> blocked_id", name="ck_user_block_not_self"),
    )

    def __repr__(self):
        return f"<UserBlock(block_id={self.block_id}, blocker_id={self.blocker_id}, blocked_id={self.blocked_id})>"
