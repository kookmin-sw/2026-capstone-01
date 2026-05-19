from datetime import datetime
from dataclasses import dataclass


@dataclass
class FcmTokenData:
    """FCM 토큰 등록 응답 DTO.

    토큰 문자열 자체는 응답에 싣지 않는다 — 클라이언트가 이미 보유 중이고,
    서버가 echo back 할 가치가 없으며 로그/응답 노출 면적을 줄이기 위함.
    """
    fcm_token_id: str
    created_at: datetime
