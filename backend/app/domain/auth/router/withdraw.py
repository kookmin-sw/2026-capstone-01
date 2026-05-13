from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from dependency_injector.wiring import Provide, inject

from app.domain.auth.service.withdraw import WithdrawService, invalidate_registered_cache
from app.domain.auth.service.exception import (
    WithdrawalAlreadyRequestedError,
    WithdrawalNotPendingError,
)
from app.core.logger import get_logger
from app.config.setting import settings
from app.container import Container


router = APIRouter(prefix="/withdraw", tags=["회원 탈퇴"])
logger = get_logger("auth.withdraw")


@router.delete("")
@inject
async def withdraw(
    request: Request,
    withdraw_service: WithdrawService = Depends(Provide[Container.withdraw_service]),
) -> JSONResponse:
    """회원 탈퇴 요청 — status 만 INACTIVE 로 전환하고 30일 후 영구 삭제 예약.

    - 즉시 삭제는 수행하지 않는다 (실제 삭제는 매일 새벽 4시 KST 스케줄러 담당).
    - 응답 후 로그인 쿠키를 즉시 만료시켜 현재 세션 종료.
    - 유예 기간 내 OAuth 재로그인 시 쿠키는 정상 발급되고 `status=withdrawal_pending`
      으로 FE 가 cancel UI 로 라우팅 → `POST /api/auth/withdraw/cancel` 호출 가능.
    """
    user_id: str = request.state.user_id

    try:
        purge_at = await withdraw_service.request_withdraw(user_id)
    except WithdrawalAlreadyRequestedError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 트랜잭션 commit 이후 캐시 무효화 — 중간 race(미커밋 ACTIVE 행 재캐싱) 차단.
    await invalidate_registered_cache(user_id)

    # commit 이후 chat 활성 세션 강제 종료 — INACTIVE 전환 후 TTL(90s) 윈도우 동안의
    # 송수신 risk 차단. 같은 race 이유로 트랜잭션 외부에서 호출.
    await withdraw_service.revoke_user_chat_state(user_id)

    response = JSONResponse(
        content={
            "message": "회원 탈퇴 요청이 접수되었습니다. 30일 후 영구 삭제됩니다.",
            "scheduled_purge_at": purge_at.isoformat(),
        }
    )
    response.delete_cookie(
        key=settings.USER_LOGIN_COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )

    logger.info("회원 탈퇴 요청 처리 완료 (user_id={})", user_id)
    return response


@router.post("/cancel")
@inject
async def cancel_withdraw(
    request: Request,
    withdraw_service: WithdrawService = Depends(Provide[Container.withdraw_service]),
) -> JSONResponse:
    """회원 탈퇴 취소 — 유예 기간 내 INACTIVE 유저를 ACTIVE 로 복구.

    경로 보호 흐름:
        - LoginCookieMiddleware: 쿠키 검증 통과 (OAuth 재로그인으로 발급된 쿠키 사용).
        - RegisterCheckMiddleware: `/api/auth/withdraw` prefix 가 EXCLUDE_PREFIXES 에
          포함되어 INACTIVE → 419 차단을 우회하므로 이 핸들러까지 안전하게 도달.

    프론트 흐름:
        탈퇴 후 30일 내 OAuth 재로그인 → 쿠키 발급 + status=withdrawal_pending →
        프론트가 cancel 화면으로 라우팅 → 본 엔드포인트 호출 → 성공 후 일반 화면.
    """
    user_id: str = request.state.user_id

    try:
        await withdraw_service.cancel_withdraw(user_id)
    except WithdrawalNotPendingError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 캐시는 별도 invalidate 불필요 — withdraw 시점에 이미 비워졌고 INACTIVE 동안 채워질
    # 일이 없으므로 (419 응답은 캐시 write 안 함). 다음 보호 경로 요청에서 미들웨어가
    # cache miss → DB → ACTIVE 확인 → REGISTERED 자연 재생성.

    logger.info("회원 탈퇴 취소 처리 완료 (user_id={})", user_id)
    return JSONResponse(
        content={"message": "회원 탈퇴 요청이 취소되었습니다."},
    )
