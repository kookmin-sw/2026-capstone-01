from typing import Any, List, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class ChatMessageData:
    """채팅 메시지 1건 DTO (MongoDB `chat_message` 문서 → 파이썬 표현).

    `sender_id` 는 시스템 메시지면 None.
    `content` 는 type 별로 다름 — text=str, image/file=dict, system={action, actor_id, target_ids?}.
    삭제된 메시지(`deleted_at != None`) 는 None.
    """
    message_id: str
    chat_room_id: str
    server_seq: int
    sender_id: Optional[str]
    type: str
    content: Any
    created_at: datetime
    edited_at: Optional[datetime]
    deleted_at: Optional[datetime]


@dataclass
class MessageListData:
    """히스토리 페이징 응답. `has_more=False` 면 `next_cursor=None`."""
    messages: List[ChatMessageData]
    has_more: bool
    next_cursor: Optional[int]


@dataclass
class MessageSentAckData:
    """메시지 송신 ACK — 발신 세션에 직송 (fan-out 미경유)."""
    client_msg_id: str
    message_id: str
    server_seq: int
    created_at: datetime
