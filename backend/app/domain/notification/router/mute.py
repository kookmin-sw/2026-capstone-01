from fastapi import APIRouter, Depends, HTTPException, Request
from dependency_injector.wiring import Provide, inject

from app.schema.common import MessageResponse
from app.domain.notification.service.mute import MuteService
from app.domain.notification.schema.mute import MuteToggleBody
from app.container import Container


router = APIRouter(prefix="/mute", tags=["알림 차단"])


# ──────────────────── 전역 ────────────────────

@router.put("/global")
@inject
async def set_global_mute(
    request: Request,
    body: MuteToggleBody,
    service: MuteService = Depends(Provide[Container.mute_service]),
) -> MessageResponse:
    """전역 알림 차단 설정 — muted=true 차단, false 해제."""
    user_id: str = request.state.user_id

    try:
        await service.set_global_mute(user_id=user_id, muted=body.muted)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return MessageResponse(
        message="모든 알림을 차단했습니다." if body.muted else "알림 차단을 해제했습니다."
    )


# ──────────────────── 방별 ────────────────────

@router.put("/rooms/{chat_room_id}")
@inject
async def set_room_mute(
    request: Request,
    chat_room_id: str,
    body: MuteToggleBody,
    service: MuteService = Depends(Provide[Container.mute_service]),
) -> MessageResponse:
    """특정 방 알림 차단 설정 — muted=true 차단, false 해제."""
    user_id: str = request.state.user_id

    try:
        await service.set_room_mute(user_id=user_id, chat_room_id=chat_room_id, muted=body.muted)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return MessageResponse(
        message="이 방의 알림을 차단했습니다." if body.muted else "이 방의 알림 차단을 해제했습니다."
    )
