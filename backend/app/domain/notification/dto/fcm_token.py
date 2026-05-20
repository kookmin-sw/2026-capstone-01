from datetime import datetime
from dataclasses import dataclass


@dataclass
class FcmTokenData:
    """토큰 문자열은 응답에 싣지 않음 — 클라가 이미 보유, 로그/응답 노출 면적 축소."""
    fcm_token_id: str
    created_at: datetime
