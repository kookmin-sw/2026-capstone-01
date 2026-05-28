"""share_token 유틸 단위 테스트.

JWT 인코드/디코드 라운드트립 + 만료/변조 케이스 검증.
"""

import pytest
import jwt
from datetime import datetime, timedelta, timezone

from app.util.share_token import ShareTokenError, decode_share_token, encode_share_token
from app.config.setting import settings


@pytest.mark.unit
class TestEncodeShareToken:
    def test_returns_token_and_future_expiry(self):
        token, expires_at = encode_share_token("TP_x")

        assert isinstance(token, str) and token  # non-empty
        assert expires_at > datetime.now(timezone.utc)


    def test_decode_roundtrip_returns_same_plan_id(self):
        token, _ = encode_share_token("TP_alpha")
        assert decode_share_token(token) == "TP_alpha"


@pytest.mark.unit
class TestDecodeShareToken:
    def test_raises_on_garbage_token(self):
        with pytest.raises(ShareTokenError):
            decode_share_token("not-a-jwt")


    def test_raises_on_wrong_secret(self):
        # 다른 비밀키로 서명한 토큰
        bad_token = jwt.encode(
            {"plan_id": "TP_x"},
            "different-secret",
            algorithm=settings.SHARE_JWT_ALGORITHM,
        )
        with pytest.raises(ShareTokenError):
            decode_share_token(bad_token)


    def test_raises_on_expired(self):
        expired_payload = {
            "plan_id": "TP_x",
            "exp": datetime.now(timezone.utc) - timedelta(seconds=10),
        }
        expired_token = jwt.encode(
            expired_payload,
            settings.SHARE_JWT_SECRET_KEY,
            algorithm=settings.SHARE_JWT_ALGORITHM,
        )
        with pytest.raises(ShareTokenError, match="만료"):
            decode_share_token(expired_token)


    def test_raises_when_payload_missing_plan_id(self):
        # plan_id 가 없는 토큰
        token = jwt.encode(
            {"foo": "bar"},
            settings.SHARE_JWT_SECRET_KEY,
            algorithm=settings.SHARE_JWT_ALGORITHM,
        )
        with pytest.raises(ShareTokenError):
            decode_share_token(token)
