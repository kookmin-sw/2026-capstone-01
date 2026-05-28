from fastapi.responses import JSONResponse
from fastapi import APIRouter, Request

from app.core.logger import get_logger
from app.config.setting import settings


router = APIRouter(prefix="/logout", tags=["로그아웃"])
logger = get_logger("auth.logout")


@router.post("")
async def logout(request: Request):
    """로그아웃 - 로그인 쿠키 만료"""
    user_id: str = request.state.user_id

    response = JSONResponse(content={"message": "로그아웃 되었습니다."})
    response.delete_cookie(
        key=settings.USER_LOGIN_COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )

    logger.debug("로그아웃: {}", user_id)
    return response
