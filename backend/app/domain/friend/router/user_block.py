from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from dependency_injector.wiring import Provide, inject

from app.schema.common import MessageResponse
from app.domain.friend.service.user_block import UserBlockService
from app.domain.friend.schema.user_block import (
    BlockUserBody,
    UserBlockResponse, UserBlockListResponse,
)
from app.domain.friend.schema.friendship import FriendPeerResponse
from app.container import Container


router = APIRouter(prefix="/blocks", tags=["유저 차단"])


@router.post("", status_code=201)
@inject
async def block_user(
    request: Request,
    body: BlockUserBody,
    service: UserBlockService = Depends(Provide[Container.user_block_service]),
) -> UserBlockResponse:
    """유저 차단"""
    user_id: str = request.state.user_id

    try:
        result = await service.block_user(user_id=user_id, target_user_id=body.target_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _to_block_response(result)


@router.delete("/{target_user_id}")
@inject
async def unblock_user(
    request: Request,
    target_user_id: str,
    service: UserBlockService = Depends(Provide[Container.user_block_service]),
) -> MessageResponse:
    """유저 차단 해제"""
    user_id: str = request.state.user_id

    try:
        await service.unblock_user(user_id=user_id, target_user_id=target_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return MessageResponse(message="차단을 해제했습니다.")


@router.get("")
@inject
async def get_blocked_users(
    request: Request,
    cursor: Optional[str] = Query(None, description="다음 페이지 커서 (block_id)"),
    service: UserBlockService = Depends(Provide[Container.user_block_service]),
) -> UserBlockListResponse:
    """내가 차단한 유저 목록"""
    user_id: str = request.state.user_id

    result = await service.get_blocked_users(user_id=user_id, cursor=cursor)
    return _to_list_response(result)


# ──────────────────── 내부 유틸 ────────────────────

def _to_block_response(dto) -> UserBlockResponse:
    return UserBlockResponse(
        block_id=dto.block_id,
        blocked=FriendPeerResponse(
            user_id=dto.blocked.user_id,
            user_name=dto.blocked.user_name,
            age=dto.blocked.age,
            gender=dto.blocked.gender,
            nationality=dto.blocked.nationality,
            profile_image_url=dto.blocked.profile_image_url,
        ),
        created_at=dto.created_at,
    )


def _to_list_response(dto) -> UserBlockListResponse:
    return UserBlockListResponse(
        items=[_to_block_response(item) for item in dto.items],
        next_cursor=dto.next_cursor,
    )
