from typing import Any, List, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class ChatMessageData:
    """채팅 메시지 1건 DTO. MongoDB `chat_message` 문서를 파이썬 표현으로 정규화.

    - `message_id`: MongoDB `_id` (MSG_{timestamp}_{uuid8})
    - `sender_id`: 시스템 메시지(`type=system`) 는 None. 유저 탈퇴 후에도 sender_id 는
      문자열로 유지되지만, 조회 시 해당 user 가 DB 에 없으면 "탈퇴한 사용자" 처리는 Router 에서.
    - `content`: type 에 따라 형태가 다름 — text 는 str, image/file 은 dict, system 은
      `{action, actor_id, target_ids?}`. 삭제된 메시지(`deleted_at != None`) 는 None.
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
    """히스토리 페이징 응답 DTO.

    - `next_cursor` 는 `messages[-1].server_seq`
    - `has_more` 가 False 면 `next_cursor` 는 None.
    """
    messages: List[ChatMessageData]
    has_more: bool
    next_cursor: Optional[int]


@dataclass
class MessageSentAckData:
    """메시지 송신 ACK DTO — 발신 세션에 직송(fan-out 미경유)."""
    client_msg_id: str
    message_id: str
    server_seq: int
    created_at: datetime
