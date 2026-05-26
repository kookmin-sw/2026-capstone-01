from urllib.parse import urlencode
import jwt
from fastapi.responses import RedirectResponse
from fastapi import APIRouter, Query, HTTPException, Depends
from dependency_injector.wiring import Provide, inject
from datetime import datetime, timedelta, timezone

from app.domain.auth.service.signup import SignupService
from app.core.oauth import OAUTH_CLIENTS
from app.core.logger import get_logger
from app.container import Container
from app.config.setting import settings
from app.config.oauth import OAuthProvider, OAUTH_APP_CONFIGS


router = APIRouter(prefix="/login/app", tags=["앱 로그인"])
logger = get_logger("auth.app_login")

# Capacitor/네이티브 앱이 받는 딥링크. 안드로이드는 이 스킴을 인텐트 필터로 처리해
# Chrome Custom Tab 에서 앱으로 복귀한다. 쿠키 전달이 불가능하므로 JWT 를 utk 쿼리
# 파라미터로 함께 내려준다.
APP_DEEP_LINK = "krip://auth/callback"


@router.get("")
async def app_login(type: OAuthProvider = Query(..., description="OAuth 제공자 타입")):
    """앱 OAuth 로그인 - 제공자 인증 페이지로 리다이렉트.

    웹과 동일한 OAuth Authorization Code 플로우지만, 콜백 경로와 최종 응답이 다르다.
    앱은 Browser.open() 으로 본 엔드포인트를 열고, 콜백에서 발급되는 딥링크를 통해
    앱으로 복귀한다.
    """
    config = OAUTH_APP_CONFIGS.get(type)
    if not config:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 OAuth 제공자: {type}")

    client_class = OAUTH_CLIENTS.get(type)
    if not client_class:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 OAuth 제공자: {type}")

    state = f"app:{type.value}"

    async with client_class(config) as client:
        authorization_url = client.get_authorization_url(state=state, user_type="callback")

    return RedirectResponse(url=authorization_url)


@router.get("/callback")
@inject
async def app_login_callback(
    code: str = Query(...), state: str = Query(...),
    signup_service: SignupService = Depends(Provide[Container.signup_service])
):
    """앱 OAuth 콜백 - 인증 코드로 JWT 발급 후 딥링크로 리다이렉트."""
    parts = state.rsplit(":", 1)
    if parts[0] != "app":
        raise HTTPException(status_code=400, detail="잘못된 state 값")

    _, provider_value = parts

    try:
        provider = OAuthProvider(provider_value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 OAuth 제공자: {provider_value}")

    config = OAUTH_APP_CONFIGS[provider]
    client_class = OAUTH_CLIENTS.get(provider)

    if not client_class:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 OAuth 제공자: {provider}")

    async with client_class(config) as client:
        access_token = await client.get_access_token(code=code, user_type="callback")
        user_info = await client.get_user_info(access_token=access_token)

    logger.info("앱 OAuth 로그인 성공: {} / {} / {} / {}", user_info.id, user_info.email, user_info.name, provider.value)

    result = await signup_service.check_and_register(
        auth_provider=provider.value,
        auth_provider_id=user_info.id,
    )

    # 앱은 쿠키 저장이 불가능해 JWT 를 utk 쿼리 파라미터로 전달한다.
    # 보호 경로 진입 시 앱이 utk 를 X-Auth-Token 헤더에 담아 보내는 책임을 진다.
    # (Authorization 헤더는 BearerTokenMiddleware 의 글로벌 ACCESS_TOKEN 자리.)
    # WITHDRAWAL_PENDING 도 토큰을 발급한다 — 프론트가 status 로 분기하고
    # RegisterCheck 미들웨어가 보호 경로에서 419 로 차단하므로 보안상 문제 없음.
    payload = {
        "user_id": result.user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.USER_LOGIN_JWT_EXPIRATION_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.USER_LOGIN_JWT_SECRET_KEY, algorithm=settings.USER_LOGIN_JWT_ALGORITHM)

    params = {"status": result.status.value, "utk": token}
    if user_info.email:
        params["email"] = user_info.email
    if user_info.name:
        params["name"] = user_info.name

    return RedirectResponse(url=f"{APP_DEEP_LINK}?{urlencode(params)}")
