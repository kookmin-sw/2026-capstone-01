from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from dependency_injector.wiring import Provide, inject

from app.schema.common import MessageResponse
from app.domain.friend.service.friendship import FriendshipService
from app.domain.friend.schema.friendship import (
    SendFriendRequestBody,
    FriendshipResponse, FriendshipListResponse, FriendPeerResponse,
)
from app.container import Container


router = APIRouter(prefix="/friendships", tags=["친구 추가,삭제,조회 기본 관리 - 차단 X"])


# ──────────────────── 친구 요청 ────────────────────

@router.post("/requests", status_code=201)
@inject
async def send_friend_request(
    request: Request,
    body: SendFriendRequestBody,
    service: FriendshipService = Depends(Provide[Container.friendship_service]),
) -> FriendshipResponse:
    """친구 요청 보내기"""
    user_id: str = request.state.user_id

    try:
        result = await service.send_request(requester_id=user_id, addressee_id=body.addressee_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _to_friendship_response(result)


@router.get("/requests/received")
@inject
async def get_received_requests(
    request: Request,
    cursor: Optional[str] = Query(None, description="다음 페이지 커서 (friendship_id)"),
    service: FriendshipService = Depends(Provide[Container.friendship_service]),
) -> FriendshipListResponse:
    """내가 받은 PENDING 친구 요청 목록"""
    user_id: str = request.state.user_id

    result = await service.get_received_requests(user_id=user_id, cursor=cursor)
    return _to_list_response(result)


@router.get("/requests/sent")
@inject
async def get_sent_requests(
    request: Request,
    cursor: Optional[str] = Query(None, description="다음 페이지 커서 (friendship_id)"),
    service: FriendshipService = Depends(Provide[Container.friendship_service]),
) -> FriendshipListResponse:
    """내가 보낸 PENDING 친구 요청 목록"""
    user_id: str = request.state.user_id

    result = await service.get_sent_requests(user_id=user_id, cursor=cursor)
    return _to_list_response(result)


@router.patch("/requests/{friendship_id}/accept")
@inject
async def accept_friend_request(
    request: Request,
    friendship_id: str,
    service: FriendshipService = Depends(Provide[Container.friendship_service]),
) -> MessageResponse:
    """친구 요청 수락"""
    user_id: str = request.state.user_id

    try:
        await service.accept_request(friendship_id=friendship_id, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return MessageResponse(message="친구 요청을 수락했습니다.")


@router.patch("/requests/{friendship_id}/reject")
@inject
async def reject_friend_request(
    request: Request,
    friendship_id: str,
    service: FriendshipService = Depends(Provide[Container.friendship_service]),
) -> MessageResponse:
    """친구 요청 거절"""
    user_id: str = request.state.user_id

    try:
        await service.reject_request(friendship_id=friendship_id, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return MessageResponse(message="친구 요청을 거절했습니다.")


@router.delete("/requests/{friendship_id}")
@inject
async def cancel_friend_request(
    request: Request,
    friendship_id: str,
    service: FriendshipService = Depends(Provide[Container.friendship_service]),
) -> MessageResponse:
    """내가 보낸 PENDING 친구 요청 취소"""
    user_id: str = request.state.user_id

    try:
        await service.cancel_request(friendship_id=friendship_id, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return MessageResponse(message="친구 요청을 취소했습니다.")


# ──────────────────── 친구 목록/삭제 ────────────────────

@router.get("")
@inject
async def get_friends(
    request: Request,
    cursor: Optional[str] = Query(None, description="다음 페이지 커서 (friendship_id)"),
    service: FriendshipService = Depends(Provide[Container.friendship_service]),
) -> FriendshipListResponse:
    """친구 목록 조회 (ACCEPTED, 최신 수락순 30개)"""
    user_id: str = request.state.user_id

    result = await service.get_friends(user_id=user_id, cursor=cursor)
    return _to_list_response(result)


@router.delete("/{friendship_id}")
@inject
async def remove_friend(
    request: Request,
    friendship_id: str,
    service: FriendshipService = Depends(Provide[Container.friendship_service]),
) -> MessageResponse:
    """친구 삭제"""
    user_id: str = request.state.user_id

    try:
        await service.remove_friend(friendship_id=friendship_id, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return MessageResponse(message="친구를 삭제했습니다.")


# ──────────────────── 내부 유틸 ────────────────────

def _to_friendship_response(dto) -> FriendshipResponse:
    return FriendshipResponse(
        friendship_id=dto.friendship_id,
        status=dto.status,
        peer=FriendPeerResponse(
            user_id=dto.peer.user_id,
            user_name=dto.peer.user_name,
            age=dto.peer.age,
            gender=dto.peer.gender,
            nationality=dto.peer.nationality,
            profile_image_url=dto.peer.profile_image_url,
        ),
        is_requester=dto.is_requester,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def _to_list_response(dto) -> FriendshipListResponse:
    return FriendshipListResponse(
        items=[_to_friendship_response(item) for item in dto.items],
        next_cursor=dto.next_cursor,
    )
