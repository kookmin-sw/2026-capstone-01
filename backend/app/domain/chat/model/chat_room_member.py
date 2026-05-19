from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import (
    Column, String, DateTime, BigInteger, Boolean, ForeignKey, Index, literal_column,
)

from app.database.session import Base


class ChatRoomMember(Base):
    """채팅방 ↔ 유저 매핑

    - `(chat_room_id, user_id)` 복합 PK — 같은 유저는 한 방에 최대 1 row.
    - 퇴장 시 물리 삭제하지 않고 `is_left=true` 로 soft delete — 재초대 시 `last_read_*`
      포인터가 그대로 유지되어 "나간 동안 쌓인 메시지" 가 정상적으로 미읽음 표기됨.
    - `last_read_message_server_seq` 는 읽음 표시(카톡 숫자 뱃지) 계산의 유일한 소스.
      `GREATEST(COALESCE(last_read_message_server_seq, 0), :new_seq)` 로 regress 방지.
    - 퇴장 플로우는 반드시 Redis `room:members:{R}` SREM → RDB UPDATE 순서 (fail-safe).
    """

    __tablename__ = "chat_room_member"

    chat_room_id = Column(String(50), ForeignKey("chat_room.chat_room_id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    joined_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_read_message_server_seq = Column(BigInteger, nullable=True)  # NULL = 아직 한 건도 안 읽음
    last_read_at = Column(DateTime(timezone=True), nullable=True)
    is_left = Column(Boolean, nullable=False, server_default="false")
    # 이 방에 한정된 알림 차단 — True 면 차단, NULL = 기본(허용). 본인이 끈 방만 row 에 True.
    notification_muted = Column(Boolean, nullable=True)

    chat_room = relationship("ChatRoom", backref="members")
    user = relationship("User", backref="chat_room_memberships")

    __table_args__ = (
        # 유저 기준 활성 방 목록 조회용 — is_left=false 부분 인덱스로 크기 최소화
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
