from fastapi import APIRouter, Depends, Request
from dependency_injector.wiring import Provide, inject

from app.schema.common import MessageResponse
from app.domain.notification.service.fcm import FcmService
from app.domain.notification.schema.fcm_token import (
    RegisterFcmTokenBody,
    UnregisterFcmTokenBody,
    FcmTokenResponse,
)
from app.container import Container


router = APIRouter(prefix="/fcm-token", tags=["FCM 토큰"])


@router.post("", status_code=201)
@inject
async def register_fcm_token(
    request: Request,
    body: RegisterFcmTokenBody,
    service: FcmService = Depends(Provide[Container.fcm_service]),
) -> FcmTokenResponse:
    """FCM 토큰 등록. 동일 token 의 owner 가 다르면 교체, 동일 (user, token) 은 no-op."""
    user_id: str = request.state.user_id

    result = await service.register_token(user_id=user_id, token=body.token)
    return FcmTokenResponse(
        fcm_token_id=result.fcm_token_id,
        created_at=result.created_at,
    )


@router.delete("")
@inject
async def unregister_fcm_token(
    request: Request,
    body: UnregisterFcmTokenBody,
    service: FcmService = Depends(Provide[Container.fcm_service]),
) -> MessageResponse:
    """FCM 토큰 해제. 본인 소유만 삭제, 없거나 타인 소유여도 idempotent (200)."""
    user_id: str = request.state.user_id

    await service.unregister_token(user_id=user_id, token=body.token)
    return MessageResponse(message="FCM 토큰을 해제했습니다.")
