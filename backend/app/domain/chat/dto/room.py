from typing import Any, List, Optional
from datetime import datetime
from dataclasses import dataclass

from app.domain.chat.model.chat_room import ChatRoomType


@dataclass
class ChatRoomPeerData:
    """1:1 방 상대방 프로필. 탈퇴자는 `user_id=None` (SET NULL 정책)."""
    user_id: Optional[str]
    user_name: Optional[str]
    profile_image_url: Optional[str] = None


@dataclass
class LastMessagePreviewData:
    """방 리스트 미리보기용 최신 메시지 요약. `content` 는 `ChatMessageData` 와 동일 다형."""
    message_id: str
    server_seq: int
    sender_id: Optional[str]
    type: str
    content: Any
    created_at: datetime


@dataclass
class ChatRoomData:
    """방 리스트 1건. DIRECT 는 `peer` / GROUP 은 `title` 채움. 신규 방은 last_message=None."""
    chat_room_id: str
    type: ChatRoomType
    title: Optional[str]
    peer: Optional[ChatRoomPeerData]
    last_message: Optional[LastMessagePreviewData]
    unread_count: int
    last_message_at: Optional[datetime]
    effective_last_at: datetime
    notification_muted: bool = False


@dataclass
class ChatRoomListData:
    items: List[ChatRoomData]
    next_cursor: Optional[str]


@dataclass
class RoomMemberData:
    """그룹 방 참여자 / 초대 가능 친구 공통 미리보기. 활성 멤버/친구만 담겨 필드 보장."""
    user_id: str
    user_name: str
    profile_image_url: Optional[str] = None


@dataclass
class RoomMemberListData:
    items: List[RoomMemberData]
