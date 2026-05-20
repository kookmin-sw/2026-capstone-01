from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import (
    Column, String, DateTime, BigInteger, Boolean, ForeignKey, Index, literal_column,
)

from app.database.session import Base


class ChatRoomMember(Base):
    """채팅방 ↔ 유저 매핑 (복합 PK).

    - 퇴장은 `is_left=true` soft delete — 재초대 시 `last_read_*` 유지로 미읽음 표기 보존.
    - `last_read_message_server_seq` 는 읽음 뱃지의 유일한 소스 (GREATEST 로 regress 방지).
    - 퇴장 플로우 순서: Redis `room:members:{R}` SREM → RDB UPDATE.
    """

    __tablename__ = "chat_room_member"

    chat_room_id = Column(String(50), ForeignKey("chat_room.chat_room_id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    joined_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_read_message_server_seq = Column(BigInteger, nullable=True)  # NULL = 아직 한 건도 안 읽음
    last_read_at = Column(DateTime(timezone=True), nullable=True)
    is_left = Column(Boolean, nullable=False, server_default="false")
    # True=차단, NULL=기본(허용). 본인이 끈 방만 True.
    notification_muted = Column(Boolean, nullable=True)

    chat_room = relationship("ChatRoom", backref="members")
    user = relationship("User", backref="chat_room_memberships")

    __table_args__ = (
        # 유저별 활성 방 조회용 — is_left=false 부분 인덱스로 크기 최소화.
        Index(
            "ix_chat_room_member_user_active",
            "user_id",
            postgresql_where=literal_column("is_left = false"),
        ),
    )

    def __repr__(self):
        return (
            f"<ChatRoomMember(chat_room_id={self.chat_room_id}, "
            f"user_id={self.user_id}, is_left={self.is_left})>"
        )
