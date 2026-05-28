from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import (
    Column, String, DateTime, BigInteger, Enum, ForeignKey, Index,
    CheckConstraint, Computed, literal_column,
)
import enum

from app.util.id_generator import generate_chat_room_id
from app.database.session import Base


class ChatRoomType(str, enum.Enum):
    DIRECT = "direct"   # 1:1 방
    GROUP = "group"     # 그룹 방


class ChatRoom(Base):
    """채팅방 메타 정보.

    - DIRECT: `(direct_user_a_id, direct_user_b_id)` canonical 정렬(`a<b`) + UNIQUE INDEX 로 중복 차단.
    - GROUP : `direct_user_*` 가 NULL (CheckConstraint).
    - `last_message_*` 는 역정규화. 실패 시 `dirty:chat_room` Redis SET 에 적재해 reconcile 이 수렴.
    - `effective_last_at` 은 GENERATED STORED — 방 리스트 정렬 인덱스 1개로 끝.

    탈퇴 정책: 유저 FK 는 모두 `ON DELETE SET NULL` — 대화/방 보존, 자리는 NULL ("탈퇴한 사용자").
    반면 `chat_room_member.user_id` 는 CASCADE — 탈퇴자 멤버십 row 만 제거.
    """

    __tablename__ = "chat_room"
    # eager_defaults=True — server-eval `updated_at` 을 RETURNING 으로 즉시 ORM 반영.
    # async 에서 lazy-load (MissingGreenlet) 회피.
    __mapper_args__ = {"eager_defaults": True}

    chat_room_id = Column(String(50), primary_key=True, default=generate_chat_room_id)
    type = Column(Enum(ChatRoomType), nullable=False)
    title = Column(String(100), nullable=True)  # direct 방은 NULL
    creator_id = Column(String(50), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)

    # 생성 시점엔 항상 a < b. 한 쪽 탈퇴 시 해당 컬럼만 NULL.
    direct_user_a_id = Column(String(50), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    direct_user_b_id = Column(String(50), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)

    # MongoDB `chat_message._id` 참조 (역정규화).
    last_message_id = Column(String(50), nullable=True)
    last_message_server_seq = Column(BigInteger, nullable=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # last_message_at NULL 이면 created_at fallback — 정렬용 단일 인덱스.
    effective_last_at = Column(
        DateTime(timezone=True),
        Computed("COALESCE(last_message_at, created_at)", persisted=True),
        nullable=False,
    )

    creator = relationship("User", foreign_keys=[creator_id], backref="created_chat_rooms")
    direct_user_a = relationship("User", foreign_keys=[direct_user_a_id], backref="direct_chat_rooms_as_a")
    direct_user_b = relationship("User", foreign_keys=[direct_user_b_id], backref="direct_chat_rooms_as_b")

    __table_args__ = (
        # DIRECT 는 (a, b) 쌍당 최대 1개 — DB 레벨에서 race 직렬화.
        Index(
            "uq_chat_room_direct_pair",
            "direct_user_a_id", "direct_user_b_id",
            unique=True,
            postgresql_where=literal_column("type = 'DIRECT'"),
        ),
        Index("ix_chat_room_effective_last_at", "effective_last_at"),
        # GROUP 은 둘 다 NULL / DIRECT 는 (둘 다 NOT NULL + a<b) 또는 (탈퇴로 일부 NULL).
        CheckConstraint(
            "("
            "  type = 'GROUP'"
            "  AND direct_user_a_id IS NULL"
            "  AND direct_user_b_id IS NULL"
            ") OR ("
            "  type = 'DIRECT'"
            "  AND direct_user_a_id IS NOT NULL"
            "  AND direct_user_b_id IS NOT NULL"
            "  AND direct_user_a_id < direct_user_b_id"
            ") OR ("
            "  type = 'DIRECT'"
            "  AND (direct_user_a_id IS NULL OR direct_user_b_id IS NULL)"
            ")",
            name="ck_chat_room_direct_pair_shape",
        ),
    )

    def __repr__(self):
        return f"<ChatRoom(chat_room_id={self.chat_room_id}, type={self.type})>"
