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
    """FCM 디바이스 토큰 등록.

    - 신규 토큰: 등록
    - 동일 토큰이 다른 user 로 등록되어 있으면 owner 교체 (계정 전환 케이스)
    - 동일 (user, token) 재등록: no-op
    """
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
    """FCM 디바이스 토큰 해제 — 클라이언트 로그아웃 시점에 호출.
    본인 소유 토큰만 삭제. 존재하지 않거나 타인 소유 토큰이어도 idempotent 하게 200."""
    user_id: str = request.state.user_id

    await service.unregister_token(user_id=user_id, token=body.token)
    return MessageResponse(message="FCM 토큰을 해제했습니다.")
