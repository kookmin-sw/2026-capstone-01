"""WebSocket 이벤트 스키마.

- 클라 → 서버 요청은 `op` (동사) — send / refresh / read.
- 서버 → 클라 이벤트는 `type` (명사) — message.new / session_revoked / ...

discriminator 필드명을 분리해야 union 해상이 가능.
"""
from typing import Annotated, Any, Literal, Optional, Union
from pydantic import BaseModel, Field
from datetime import datetime

from app.domain.chat.model.chat_message import MessageType


# ════════════════════════════════════════════════════════════════════
# 클라 → 서버 요청 (`op` discriminator)
# ════════════════════════════════════════════════════════════════════

class SendOp(BaseModel):
    """메시지 송신 요청."""
    op: Literal["send"]
    room_id: str = Field(..., description="보낼 방 ID")
    client_msg_id: str = Field(..., description="클라 UUID — 동일 ID 재전송은 dedupe 차단")
    type: MessageType = Field(MessageType.TEXT, description="메시지 종류")
    content: str = Field(..., max_length=2000, description="본문 (2000자 제한)")


class RefreshOp(BaseModel):
    """JWT access 토큰 갱신 요청."""
    op: Literal["refresh"]
    token: str = Field(..., description="새 access token")


class ReadOp(BaseModel):
    """읽음 포인터 갱신 — `up_to_server_seq` 까지 읽음 표시."""
    op: Literal["read"]
    room_id: str = Field(..., description="읽음 처리할 방 ID")
    up_to_server_seq: int = Field(
        ..., ge=1,
        description="여기까지 읽음. regress 는 DB GREATEST 가 무시",
    )


ClientRequest = Annotated[
    Union[SendOp, RefreshOp, ReadOp],
    Field(discriminator="op"),
]


# ════════════════════════════════════════════════════════════════════
# 서버 → 클라 이벤트 (`type` discriminator)
# ════════════════════════════════════════════════════════════════════

class ConnectedEvent(BaseModel):
    """WS 연결 직후 서버가 첫 번째로 내려주는 세션 정보."""
    type: Literal["connected"]
    session_id: str = Field(..., description="서버가 발급한 세션 ID")


class MessageSentEvent(BaseModel):
    """송신한 메시지의 서버 확정 ACK — 발신 세션에만 직송."""
    type: Literal["message.sent"]
    client_msg_id: str = Field(..., description="요청 시 넘긴 client_msg_id")
    message_id: str = Field(..., description="MongoDB _id")
    server_seq: int = Field(..., description="방 내부 단조 시퀀스")
    created_at: datetime = Field(..., description="서버 확정 시각")


class MessageBody(BaseModel):
    """`message.new` 의 본문 — MongoDB 문서 스키마와 동일."""
    message_id: str
    chat_room_id: str
    server_seq: int
    sender_id: Optional[str] = None
    type: str
    content: Any = Field(
        ...,
        description="type 별 다형. text=str / image·file=dict / system=SystemContent / 삭제=null",
    )
    created_at: datetime


class MessageNewEvent(BaseModel):
    """방에 새 메시지가 발행됨."""
    type: Literal["message.new"]
    sender_session_id: str = Field(..., description="발신 세션 — 자기 에코 skip 필터용")
    message: MessageBody = Field(..., description="본문")


class SessionRevokedEvent(BaseModel):
    """특정 session_id 강제 종료 — 자기 세션이면 클라가 close(4001)."""
    type: Literal["session_revoked"]
    session_id: str = Field(..., description="종료 대상 세션 ID")


class AuthExpiredEvent(BaseModel):
    """JWT refresh 실패 / `sess:*` 부재 — 클라는 재로그인 플로우로."""
    type: Literal["auth_expired"]


class ServerErrorEvent(BaseModel):
    """일시적 서버 에러 — 클라는 backoff 후 재접속(1012)."""
    type: Literal["server_error"]
    reason: Optional[str] = Field(None, description="디버깅용 사유 (내부 로그와 매칭)")


class ServerRestartEvent(BaseModel):
    """노드 graceful shutdown 알림 — 클라 3~5s backoff 후 재접속."""
    type: Literal["server_restart"]


class MessageUpdatedEvent(BaseModel):
    """메시지 편집 완료 — 방 구독자 전체에 브로드캐스트."""
    type: Literal["message.updated"]
    sender_session_id: Optional[str] = Field(
        None, description="편집 트리거 세션 ID — 본인 에코 차단용",
    )
    message_id: str = Field(..., description="편집된 메시지 ID")
    content: Any = Field(..., description="새 본문")
    edited_at: datetime = Field(..., description="편집 시각")


class MessageDeletedEvent(BaseModel):
    """메시지 soft delete — 방 구독자 전체에 브로드캐스트. 클라는 "삭제된 메시지입니다" 로 치환."""
    type: Literal["message.deleted"]
    sender_session_id: Optional[str] = Field(
        None, description="삭제 트리거 세션 ID — 본인 에코 차단용",
    )
    message_id: str = Field(..., description="삭제된 메시지 ID")
    deleted_at: datetime = Field(..., description="삭제 시각")


class RoomJoinedEvent(BaseModel):
    """방이 새로 생성되었거나 초대됨 — WS 의 로컬 dict 에 해당 방 등록."""
    type: Literal["room_joined"]
    room_id: str = Field(..., description="참여할 방 ID")


class RoomLeftEvent(BaseModel):
    """본인이 방에서 나가거나 강퇴됨 — WS 의 로컬 dict 에서 해당 방 구독 해제."""
    type: Literal["room_left"]
    room_id: str = Field(..., description="떠나는 방 ID")


class ReadEvent(BaseModel):
    """방의 다른 세션/유저에게 "누가 어디까지 읽었다" 를 알림."""
    type: Literal["read"]
    user_id: str = Field(..., description="읽음 처리한 유저")
    up_to_server_seq: int = Field(..., description="최종 반영된 last_read_message_server_seq")
    sender_session_id: str = Field(
        ..., description="발신 세션 ID — 발신자 본인 WS 자기 에코 차단용",
    )


class ReadAckEvent(BaseModel):
    """read op 처리 성공 — 발신 세션 직송."""
    type: Literal["read_ack"]
    room_id: str = Field(..., description="읽음 처리된 방 ID")
    up_to_server_seq: int = Field(..., description="최종 반영된 last_read_message_server_seq")


class ReadFailedEvent(BaseModel):
    """read op 처리 실패 — 발신 세션 직송. 사유는 reason 문자열."""
    type: Literal["read_failed"]
    room_id: str = Field(..., description="실패한 방 ID")
    reason: str = Field(..., description="실패 사유")


class UnreadSyncedEvent(BaseModel):
    """WS 연결 직후 또는 백그라운드 복구 완료 시 unread 카운트 동기화."""
    type: Literal["unread_synced"]
    counts: dict[str, int] = Field(..., description="{room_id: count}. 값은 0..999 (999+ 캡)")


ServerEvent = Annotated[
    Union[
        ConnectedEvent,
        MessageSentEvent,
        MessageNewEvent,
        MessageUpdatedEvent,
        MessageDeletedEvent,
        SessionRevokedEvent,
        AuthExpiredEvent,
        ServerErrorEvent,
        ServerRestartEvent,
        RoomJoinedEvent,
        RoomLeftEvent,
        ReadEvent,
        ReadAckEvent,
        ReadFailedEvent,
        UnreadSyncedEvent,
    ],
    Field(discriminator="type"),
]


# ════════════════════════════════════════════════════════════════════
# 시스템 메시지 content payload (`action` discriminator)
# ════════════════════════════════════════════════════════════════════
# `message.type == "system"` 일 때의 `content` 모양. actor 가 탈퇴하면 null (SET NULL 정책).
# `target_ids` 는 join/kick 에만 — created/leave 는 actor 본인이 곧 대상이라 생략.

class SystemContentCreated(BaseModel):
    """방이 처음 생성됨 — `actor_id` 가 creator."""
    action: Literal["created"]
    actor_id: Optional[str] = Field(..., description="방을 만든 유저. 이후 탈퇴하면 null")


class SystemContentJoin(BaseModel):
    """새 멤버 합류 — `actor_id` 가 `target_ids` 를 초대."""
    action: Literal["join"]
    actor_id: Optional[str] = Field(..., description="초대를 수행한 유저. 이후 탈퇴하면 null")
    target_ids: list[str] = Field(
        ..., min_length=1, description="새로 합류한 유저 ID 목록 — 항상 1명 이상",
    )


class SystemContentLeave(BaseModel):
    """멤버 본인이 방을 떠남 — `actor_id` 본인이 대상."""
    action: Literal["leave"]
    actor_id: Optional[str] = Field(..., description="방을 나간 유저. 나가는 동시에 탈퇴한 케이스는 null")


class SystemContentKick(BaseModel):
    """강퇴 — `actor_id`(그룹 creator) 가 `target_ids` 를 내보냄."""
    action: Literal["kick"]
    actor_id: Optional[str] = Field(..., description="강퇴를 실행한 creator. 이후 탈퇴하면 null")
    target_ids: list[str] = Field(
        ..., min_length=1, description="강퇴당한 유저 ID 목록 — 현재 구현은 단건이지만 스키마는 복수 대응",
    )


SystemContent = Annotated[
    Union[
        SystemContentCreated,
        SystemContentJoin,
        SystemContentLeave,
        SystemContentKick,
    ],
    Field(discriminator="action"),
]
