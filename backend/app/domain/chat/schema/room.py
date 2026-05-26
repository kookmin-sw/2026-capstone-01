from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime

from app.domain.chat.model.chat_room import ChatRoomType


# 본인 포함 100명. fan-out 지연 + SADD 크기 고려한 협의 값.
_MAX_GROUP_MEMBERS = 99
_MAX_INVITE_BATCH = 50


# ──────────────────── Request ────────────────────

class CreateDirectRoomBody(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "peer_user_id": "USER_1700000000_abcdef12",
            }
        }
    )

    peer_user_id: str = Field(..., description="대화할 상대 유저 ID")


class CreateGroupRoomBody(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "캡스톤 디자인 7팀",
                "member_ids": [
                    "USER_1700000000_abcdef12",
                    "USER_1700000001_abcdef13",
                ],
            }
        }
    )

    title: str = Field(..., min_length=1, max_length=100, description="방 제목")
    member_ids: List[str] = Field(
        ...,
        min_length=1,
        max_length=_MAX_GROUP_MEMBERS,
        description="초대할 유저 ID 목록 (본인 제외, 친구만 허용)",
    )


class InviteMembersBody(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_ids": ["USER_1700000002_abcdef14"],
            }
        }
    )

    user_ids: List[str] = Field(
        ...,
        min_length=1,
        max_length=_MAX_INVITE_BATCH,
        description="초대할 유저 ID 목록 (친구만 허용)",
    )


class KickMemberBody(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "USER_1700000002_abcdef14",
            }
        }
    )

    user_id: str = Field(..., description="강퇴할 유저 ID (요청자는 creator 여야 함)")


# ──────────────────── Response — 그룹 관리 액션 ────────────────────

class InviteMembersResponse(BaseModel):
    """invite 엔드포인트 응답 — 실제로 초대된 user_id 만 반환 (이미 멤버/비친구 제외)."""
    invited_user_ids: List[str] = Field(..., description="이번 호출로 초대된 user_id 목록")
    skipped_already_member: List[str] = Field(
        default_factory=list,
        description="이미 활성 멤버라 skip 된 user_id 목록",
    )


# ──────────────────── Response — 내부 구성요소 ────────────────────

class ChatRoomPeerResponse(BaseModel):
    """1:1 방 상대방 프로필. 탈퇴한 경우 필드가 모두 null — 클라는 '탈퇴한 사용자' 로 표시."""
    user_id: Optional[str] = Field(None, description="상대 유저 ID (탈퇴 시 null)")
    user_name: Optional[str] = Field(None, description="상대 닉네임 (탈퇴 시 null)")
    profile_image_url: Optional[str] = Field(None, description="프로필 이미지 URL (없으면 null)")


class LastMessagePreviewResponse(BaseModel):
    """방 리스트 미리보기용 최신 메시지 요약."""
    message_id: str = Field(..., description="메시지 ID (MongoDB _id)")
    server_seq: int = Field(..., description="방 내부 단조 시퀀스")
    sender_id: Optional[str] = Field(None, description="보낸 유저 ID (시스템 메시지면 null)")
    type: str = Field(..., description="메시지 종류 (text / image / file / system)")
    content: Optional[Any] = Field(
        None,
        description=(
            "미리보기 본문 — type 에 따라 다름. text=str, image/file=dict, system=object, "
            "삭제된 메시지는 null"
        ),
    )
    created_at: datetime = Field(..., description="보낸 시각")


# ──────────────────── Response — 방 본체 ────────────────────

class ChatRoomResponse(BaseModel):
    chat_room_id: str = Field(..., description="방 고유 ID")
    type: ChatRoomType = Field(..., description="방 종류 (direct / group)")
    title: Optional[str] = Field(None, description="방 제목 (그룹방만, direct 는 null)")
    peer: Optional[ChatRoomPeerResponse] = Field(
        None, description="1:1 방의 상대방 프로필 (group 은 null)"
    )
    last_message: Optional[LastMessagePreviewResponse] = Field(
        None, description="최신 메시지 미리보기 (신규 방은 null)"
    )
    unread_count: int = Field(..., description="현재 유저의 미읽음 메시지 수")
    last_message_at: Optional[datetime] = Field(None, description="최신 메시지 시각")
    effective_last_at: datetime = Field(
        ..., description="정렬 기준 시각 — last_message_at 없으면 created_at 으로 fallback"
    )
    notification_muted: bool = Field(
        ..., description="이 방의 알림 차단 여부 (true = 이 방 푸시 차단)"
    )


class ChatRoomListResponse(BaseModel):
    items: List[ChatRoomResponse] = Field(..., description="방 리스트")
    next_cursor: Optional[str] = Field(
        None, description="다음 페이지 커서 (마지막 페이지면 null)"
    )


# ──────────────────── Response — 참여자 / 초대 가능 친구 ────────────────────

class RoomMemberResponse(BaseModel):
    """그룹 방 참여자 / 초대 가능 친구 목록의 공통 미리보기 응답."""
    user_id: str = Field(..., description="유저 ID")
    user_name: str = Field(..., description="유저 이름")
    profile_image_url: Optional[str] = Field(None, description="프로필 이미지 URL (없으면 null)")


class RoomMemberListResponse(BaseModel):
    items: List[RoomMemberResponse] = Field(..., description="유저 목록")
