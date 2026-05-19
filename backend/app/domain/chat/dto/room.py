from typing import Any, List, Optional
from datetime import datetime
from dataclasses import dataclass

from app.domain.chat.model.chat_room import ChatRoomType


@dataclass
class ChatRoomPeerData:
    """1:1 방의 상대방 프로필 DTO.

    탈퇴 정책(ON DELETE SET NULL) 에 따라 상대가 탈퇴한 경우
    `user_id` 가 None — 클라는 이 경우 "탈퇴한 사용자" 로 표시한다.
    """
    user_id: Optional[str]
    user_name: Optional[str]
    profile_image_url: Optional[str] = None


@dataclass
class LastMessagePreviewData:
    """방 리스트 미리보기용 최신 메시지 요약.

    `content` 는 `ChatMessageData.content` 와 동일한 다형 — type 에 따라
    text=str, image/file=dict, system=`{action, actor_id, target_ids?}`,
    삭제된 메시지(`deleted_at != null`) 는 None.
    """
    message_id: str
    server_seq: int
    sender_id: Optional[str]
    type: str              # MessageType.value — "text" | "image" | "file" | "system"
    content: Any
    created_at: datetime


@dataclass
class ChatRoomData:
    """방 리스트 1건 응답 DTO.

    - `type='DIRECT'` 이면 `peer` 채움, `title` 은 None.
    - `type='GROUP'` 이면 `title` 채움, `peer` 는 None
    - `last_message` 는 아직 메시지가 없는 신규 방은 None.
    - `unread_count` 는 Redis `unread:{user_id}` 에서 병합 (없으면 0).
    """
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
    """방 리스트 응답 DTO."""
    items: List[ChatRoomData]
    next_cursor: Optional[str]


@dataclass
class RoomMemberData:
    """그룹 방 참여자 / 초대 가능 친구 목록의 공통 미리보기 DTO.

    활성 멤버 (is_left=false) 또는 ACCEPTED 친구만 담기므로 user_id/user_name 은 항상 보장.
    """
    user_id: str
    user_name: str
    profile_image_url: Optional[str] = None


@dataclass
class RoomMemberListData:
    """참여자 / 초대 가능 친구 목록 응답 DTO."""
    items: List[RoomMemberData]
