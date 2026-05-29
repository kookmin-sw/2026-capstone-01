from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from dependency_injector.wiring import Provide, inject

from app.domain.chat.service.room import RoomService
from app.domain.chat.service.message_history import MessageHistoryService
from app.domain.chat.service.exception import ChatRoomNotFoundError
from app.domain.chat.schema.room import (
    ChatRoomListResponse,
    ChatRoomPeerResponse,
    ChatRoomResponse,
    CreateDirectRoomBody,
    CreateGroupRoomBody,
    InviteMembersBody,
    InviteMembersResponse,
    KickMemberBody,
    LastMessagePreviewResponse,
    RoomMemberListResponse,
    RoomMemberResponse,
)
from app.domain.chat.schema.message import ChatMessageResponse, MessageHistoryResponse
from app.container import Container


router = APIRouter(prefix="/rooms", tags=["채팅 - 방/메시지"])


# ──────────────────── 방 생성 ────────────────────

@router.post("/direct", status_code=201)
@inject
async def create_direct_room(
    request: Request,
    body: CreateDirectRoomBody,
    service: RoomService = Depends(Provide[Container.room_service]),
) -> ChatRoomResponse:
    """1:1 방 생성 (idempotent — 같은 상대면 기존 방 반환)."""
    user_id: str = request.state.user_id

    try:
        result = await service.create_direct_room(
            me_id=user_id, peer_user_id=body.peer_user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _to_room_response(result)


# ──────────────────── 그룹 방 생성 ────────────────────

@router.post("/group", status_code=201)
@inject
async def create_group_room(
    request: Request,
    body: CreateGroupRoomBody,
    service: RoomService = Depends(Provide[Container.room_service]),
) -> ChatRoomResponse:
    """그룹 방 생성 (creator 포함 최대 100명). 멤버는 친구 관계여야 함."""
    user_id: str = request.state.user_id

    try:
        result = await service.create_group_room(
            me_id=user_id, title=body.title, member_ids=body.member_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _to_room_response(result)


# ──────────────────── 멤버 초대 ────────────────────

@router.post("/{chat_room_id}/invite")
@inject
async def invite_members(
    request: Request,
    chat_room_id: str,
    body: InviteMembersBody,
    service: RoomService = Depends(Provide[Container.room_service]),
) -> InviteMembersResponse:
    """그룹 방에 멤버 초대. 친구만 가능, 이미 멤버는 스킵."""
    user_id: str = request.state.user_id

    try:
        invited, skipped = await service.invite_members(
            me_id=user_id, room_id=chat_room_id, user_ids=body.user_ids,
        )
    except ChatRoomNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return InviteMembersResponse(
        invited_user_ids=invited,
        skipped_already_member=skipped,
    )


# ──────────────────── 퇴장 ────────────────────

@router.post("/{chat_room_id}/leave", status_code=204)
@inject
async def leave_room(
    request: Request,
    chat_room_id: str,
    service: RoomService = Depends(Provide[Container.room_service]),
) -> None:
    """그룹 방에서 본인 퇴장. direct 방은 거절."""
    user_id: str = request.state.user_id

    try:
        await service.leave_room(me_id=user_id, room_id=chat_room_id)
    except ChatRoomNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────── 강퇴 ────────────────────

@router.post("/{chat_room_id}/kick", status_code=204)
@inject
async def kick_member(
    request: Request,
    chat_room_id: str,
    body: KickMemberBody,
    service: RoomService = Depends(Provide[Container.room_service]),
) -> None:
    """그룹 방에서 특정 멤버 강퇴. creator 전용."""
    user_id: str = request.state.user_id

    try:
        await service.kick_member(
            me_id=user_id, room_id=chat_room_id, target_user_id=body.user_id,
        )
    except ChatRoomNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────── 방 리스트 ────────────────────

@router.get("")
@inject
async def list_rooms(
    request: Request,
    service: MessageHistoryService = Depends(Provide[Container.message_history_service]),
) -> ChatRoomListResponse:
    """내가 속한 활성 방 리스트 (effective_last_at 최신순, 최대 500개)."""
    user_id: str = request.state.user_id
    result = await service.list_rooms(me_id=user_id)
    return _to_list_response(result)


# ──────────────────── 단건 방 조회 ────────────────────

@router.get("/{chat_room_id}")
@inject
async def get_room(
    request: Request,
    chat_room_id: str,
    service: MessageHistoryService = Depends(Provide[Container.message_history_service]),
) -> ChatRoomResponse:
    """방 1건 상세 조회 — `room_joined` WS 이벤트 수신 후 메타 fetch 용."""
    user_id: str = request.state.user_id

    try:
        result = await service.get_room(me_id=user_id, room_id=chat_room_id)
    except ChatRoomNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _to_room_response(result)


# ──────────────────── 그룹 방 참여자 목록 ────────────────────

@router.get("/{chat_room_id}/members")
@inject
async def list_room_members(
    request: Request,
    chat_room_id: str,
    service: MessageHistoryService = Depends(Provide[Container.message_history_service]),
) -> RoomMemberListResponse:
    """그룹 방의 활성 참여자 프로필 목록 (joined_at 오름차순). 1:1 방은 400."""
    user_id: str = request.state.user_id

    try:
        result = await service.list_room_members(me_id=user_id, room_id=chat_room_id)
    except ChatRoomNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _to_member_list_response(result)


# ──────────────────── 그룹 방 초대 가능 친구 목록 ────────────────────

@router.get("/{chat_room_id}/invitable-friends")
@inject
async def list_invitable_friends(
    request: Request,
    chat_room_id: str,
    service: MessageHistoryService = Depends(Provide[Container.message_history_service]),
) -> RoomMemberListResponse:
    """방에 아직 들어오지 않은 내 친구 프로필 목록 — 그룹 방 초대 UI 용."""
    user_id: str = request.state.user_id

    try:
        result = await service.list_invitable_friends(me_id=user_id, room_id=chat_room_id)
    except ChatRoomNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _to_member_list_response(result)


# ──────────────────── 메시지 히스토리 ────────────────────

@router.get("/{chat_room_id}/messages")
@inject
async def get_messages(
    request: Request,
    chat_room_id: str,
    before_server_seq: Optional[int] = Query(
        None, description="이 seq 미만의 메시지를 최신순으로 - 위로 스크롤",
    ),
    after_server_seq: Optional[int] = Query(
        None, description="이 seq 초과의 메시지를 과거순으로 - 아래로 스크롤",
    ),
    limit: int = Query(50, ge=1, le=200, description="페이지 크기"),
    service: MessageHistoryService = Depends(Provide[Container.message_history_service]),
) -> MessageHistoryResponse:
    """방의 메시지 히스토리. `before_server_seq` / `after_server_seq` 중 정확히 하나만 지정."""
    user_id: str = request.state.user_id

    if (before_server_seq is None) == (after_server_seq is None):
        raise HTTPException(
            status_code=400,
            detail="before_server_seq 또는 after_server_seq 중 하나만 지정해야 합니다.",
        )

    try:
        if before_server_seq is not None:
            result = await service.find_messages_before(
                me_id=user_id,
                room_id=chat_room_id,
                before_server_seq=before_server_seq,
                limit=limit,
            )
        else:
            result = await service.find_messages_after(
                me_id=user_id,
                room_id=chat_room_id,
                after_server_seq=after_server_seq,
                limit=limit,
            )
    except ChatRoomNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _to_message_history_response(result)


# ──────────────────── 내부 변환 유틸 ────────────────────

def _to_room_response(dto) -> ChatRoomResponse:
    peer = (
        ChatRoomPeerResponse(
            user_id=dto.peer.user_id,
            user_name=dto.peer.user_name,
            profile_image_url=dto.peer.profile_image_url,
        )
        if dto.peer is not None else None
    )
    last = (
        LastMessagePreviewResponse(
            message_id=dto.last_message.message_id,
            server_seq=dto.last_message.server_seq,
            sender_id=dto.last_message.sender_id,
            type=dto.last_message.type,
            content=dto.last_message.content,
            created_at=dto.last_message.created_at,
        )
        if dto.last_message is not None else None
    )
    return ChatRoomResponse(
        chat_room_id=dto.chat_room_id,
        type=dto.type,
        title=dto.title,
        peer=peer,
        last_message=last,
        unread_count=dto.unread_count,
        last_message_at=dto.last_message_at,
        effective_last_at=dto.effective_last_at,
        notification_muted=dto.notification_muted,
    )


def _to_list_response(dto) -> ChatRoomListResponse:
    return ChatRoomListResponse(
        items=[_to_room_response(item) for item in dto.items],
        next_cursor=dto.next_cursor,
    )


def _to_message_response(dto) -> ChatMessageResponse:
    return ChatMessageResponse(
        message_id=dto.message_id,
        chat_room_id=dto.chat_room_id,
        server_seq=dto.server_seq,
        sender_id=dto.sender_id,
        type=dto.type,
        content=dto.content,
        created_at=dto.created_at,
        edited_at=dto.edited_at,
        deleted_at=dto.deleted_at,
    )


def _to_member_list_response(dto) -> RoomMemberListResponse:
    return RoomMemberListResponse(
        items=[
            RoomMemberResponse(
                user_id=item.user_id,
                user_name=item.user_name,
                profile_image_url=item.profile_image_url,
            )
            for item in dto.items
        ],
    )


def _to_message_history_response(dto) -> MessageHistoryResponse:
    return MessageHistoryResponse(
        messages=[_to_message_response(m) for m in dto.messages],
        has_more=dto.has_more,
        next_cursor=dto.next_cursor,
    )
