from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, Index, CheckConstraint, literal_column
import enum

from app.util.id_generator import generate_friendship_id
from app.database.session import Base


class FriendshipStatus(str, enum.Enum):
    PENDING = "pending"      # 요청 대기
    ACCEPTED = "accepted"    # 수락
    REJECTED = "rejected"    # 거절


class Friendship(Base):
    """친구 관계 (요청 대기 / 수락 / 거절)

    - requester_id: 친구 요청을 보낸 유저
    - addressee_id: 요청을 받은 유저
    - 두 유저 간 관계는 방향과 무관하게 유일 — canonical functional unique index
      (LEAST, GREATEST) 로 A→B 와 B→A 동시 INSERT 경합을 DB 레벨에서 차단
    - 자기 자신에게 요청 불가 (CheckConstraint)
    - 차단은 별도 테이블(user_block)에서 관리
    """

    __tablename__ = "friendship"
    # `eager_defaults=True` — server-eval `updated_at` 을 RETURNING 으로 즉시 ORM 반영.
    # async 환경에서 lazy-load (MissingGreenlet) 회피 표준 패턴.
    __mapper_args__ = {"eager_defaults": True}

    friendship_id = Column(String(50), primary_key=True, default=generate_friendship_id)
    requester_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)  # 요청 보낸 유저
    addressee_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)  # 요청 받은 유저
    status = Column(Enum(FriendshipStatus), nullable=False, default=FriendshipStatus.PENDING)  # 관계 상태
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    requester = relationship("User", foreign_keys=[requester_id], backref="sent_friendships")
    addressee = relationship("User", foreign_keys=[addressee_id], backref="received_friendships")

    __table_args__ = (
        Index(
            "uq_friendship_canonical_pair",
            func.least(literal_column("requester_id"), literal_column("addressee_id")),
            func.greatest(literal_column("requester_id"), literal_column("addressee_id")),
            unique=True,
        ), # 동시 친구 관계 중복 생성 제약 조건
        Index("ix_friendship_requester_status", "requester_id", "status"),
        Index("ix_friendship_addressee_status", "addressee_id", "status"),
        CheckConstraint("requester_id <> addressee_id", name="ck_friendship_not_self"),
    )

    def __repr__(self):
        return f"<Friendship(friendship_id={self.friendship_id}, requester_id={self.requester_id}, addressee_id={self.addressee_id}, status={self.status})>"
