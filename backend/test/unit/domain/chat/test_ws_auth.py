"""채팅 WebSocket 인증 헬퍼 단위 테스트.

WS 업그레이드는 BaseHTTPMiddleware 를 거치지 않아 인증을 핸들러 모듈 내부에서 직접
수행한다 (`ws.py`). 이번에 cookie-only 였던 흐름이 ``Sec-WebSocket-Protocol`` 기반의
앱 채널을 추가로 지원하게 됐다. 각 헬퍼는 순수 함수라 Redis / DB 없이 mock WebSocket
하나로 전 분기를 cover 한다.

- ``_is_allowed_origin``        : FE + LOCAL_FE + APP_ALLOWED_ORIGINS 합집합
- ``_ws_subprotocols``          : Sec-WebSocket-Protocol 헤더 파싱
- ``_extract_jwt``              : 쿠키 → subprotocol 우선순위
- ``_select_accept_subprotocol``: krip.chat.v1 echo, auth.* 절대 echo 금지
- ``_verify_jwt``               : 서명/만료 검증 + user_id/jti 추출
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import jwt
import pytest

from app.config.setting import settings
from app.domain.chat.router.ws import (
    SUBPROTOCOL_AUTH_PREFIX,
    SUBPROTOCOL_VERSION,
    _extract_jwt,
    _is_allowed_origin,
    _select_accept_subprotocol,
    _verify_jwt,
    _ws_subprotocols,
)


pytestmark = pytest.mark.unit


# ──────────────────────────────────────────────────────────────────
# WS mock 헬퍼 — headers / cookies 두 매핑만 노출하면 충분
# ──────────────────────────────────────────────────────────────────

def _make_ws(
    *,
    cookie_token: str | None = None,
    subprotocols: list[str] | None = None,
) -> MagicMock:
    """헬퍼들이 보는 인터페이스만 갖춘 가짜 WebSocket."""
    ws = MagicMock(name="websocket")
    ws.headers = {}
    if subprotocols is not None:
        # 클라가 보내는 헤더는 `, ` 로 join — 헬퍼는 소문자 키로 조회
        ws.headers["sec-websocket-protocol"] = ", ".join(subprotocols)
    ws.cookies = {}
    if cookie_token is not None:
        ws.cookies[settings.USER_LOGIN_COOKIE_NAME] = cookie_token
    return ws


def _make_token(user_id: str | None = "USER_a", jti: str | None = None,
                expires_in: timedelta = timedelta(hours=1),
                secret: str | None = None) -> str:
    payload: dict = {
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + expires_in,
    }
    if user_id is not None:
        payload["user_id"] = user_id
    if jti is not None:
        payload["jti"] = jti
    return jwt.encode(
        payload,
        secret or settings.USER_LOGIN_JWT_SECRET_KEY,
        algorithm=settings.USER_LOGIN_JWT_ALGORITHM,
    )


# ──────────────────────────────────────────────────────────────────
# _is_allowed_origin
# ──────────────────────────────────────────────────────────────────

class TestIsAllowedOrigin:
    def test_allows_configured_frontend_origin(self):
        assert _is_allowed_origin(settings.FRONTEND_URL) is True

    def test_allows_local_frontend_origin(self):
        assert _is_allowed_origin(settings.LOCAL_FRONTEND_URL) is True

    def test_allows_app_origin_from_whitelist(self, monkeypatch):
        """APP_ALLOWED_ORIGINS 쉼표 리스트가 set 으로 파싱되어 합집합에 들어가는지 확인."""
        monkeypatch.setattr(
            settings, "APP_ALLOWED_ORIGINS",
            "capacitor://localhost, https://localhost",
        )
        assert _is_allowed_origin("capacitor://localhost") is True
        assert _is_allowed_origin("https://localhost") is True

    def test_rejects_unknown_origin(self):
        assert _is_allowed_origin("https://evil.example.com") is False

    def test_rejects_none(self):
        """Origin 헤더 부재 — 브라우저 외 임의 클라이언트 차단."""
        assert _is_allowed_origin(None) is False


# ──────────────────────────────────────────────────────────────────
# _ws_subprotocols
# ──────────────────────────────────────────────────────────────────

class TestWsSubprotocolsParsing:
    def test_parses_comma_separated_protocols_with_whitespace(self):
        ws = _make_ws(subprotocols=["krip.chat.v1", "auth.abc.def"])

        assert _ws_subprotocols(ws) == ["krip.chat.v1", "auth.abc.def"]

    def test_returns_empty_list_when_header_absent(self):
        ws = _make_ws()
        assert _ws_subprotocols(ws) == []

    def test_drops_empty_segments(self):
        """비어 있는 segment (` ,, `) 는 무시 — 헬퍼가 strip 후 falsy 필터링."""
        ws = MagicMock()
        ws.headers = {"sec-websocket-protocol": "krip.chat.v1, , auth.x"}
        ws.cookies = {}
        assert _ws_subprotocols(ws) == ["krip.chat.v1", "auth.x"]


# ──────────────────────────────────────────────────────────────────
# _extract_jwt — 쿠키 → subprotocol 우선순위
# ──────────────────────────────────────────────────────────────────

class TestExtractJwt:
    def test_returns_cookie_token_when_present(self):
        ws = _make_ws(cookie_token="cookie-tok")
        assert _extract_jwt(ws) == "cookie-tok"

    def test_falls_back_to_subprotocol_auth_prefix(self):
        ws = _make_ws(subprotocols=[SUBPROTOCOL_VERSION, f"{SUBPROTOCOL_AUTH_PREFIX}sub-tok"])
        assert _extract_jwt(ws) == "sub-tok"

    def test_cookie_wins_when_both_present(self):
        """주석에 명시된 우선순위 — 기존 웹 동작을 그대로 보존."""
        ws = _make_ws(
            cookie_token="cookie-tok",
            subprotocols=[SUBPROTOCOL_VERSION, f"{SUBPROTOCOL_AUTH_PREFIX}sub-tok"],
        )
        assert _extract_jwt(ws) == "cookie-tok"

    def test_returns_none_when_neither(self):
        ws = _make_ws()
        assert _extract_jwt(ws) is None

    def test_returns_none_when_only_version_subprotocol(self):
        """클라가 인증 subprotocol 없이 버전만 보낸 경우 — 토큰 없음으로 판정."""
        ws = _make_ws(subprotocols=[SUBPROTOCOL_VERSION])
        assert _extract_jwt(ws) is None

    def test_returns_none_when_auth_prefix_is_empty(self):
        """`auth.` 만 있고 토큰 부분이 비면 None — close(4001) 분기로 정확히 전달."""
        ws = _make_ws(subprotocols=[SUBPROTOCOL_VERSION, "auth."])
        assert _extract_jwt(ws) is None


# ──────────────────────────────────────────────────────────────────
# _select_accept_subprotocol — 응답 echo 정책
# ──────────────────────────────────────────────────────────────────

class TestSelectAcceptSubprotocol:
    def test_echoes_krip_chat_v1_when_requested(self):
        ws = _make_ws(subprotocols=[SUBPROTOCOL_VERSION, f"{SUBPROTOCOL_AUTH_PREFIX}t"])
        assert _select_accept_subprotocol(ws) == SUBPROTOCOL_VERSION

    def test_never_echoes_auth_subprotocol(self):
        """auth.<jwt> 만 보내고 버전이 없으면 None — 토큰을 응답 헤더로 절대 노출하지 않는다.

        브라우저가 ``krip.chat.v1`` 없이 ``auth.*`` 만 보내는 일은 클라 계약 위반이지만,
        만일에도 토큰 echo 가 발생하지 않음을 명시적으로 가드.
        """
        ws = _make_ws(subprotocols=[f"{SUBPROTOCOL_AUTH_PREFIX}leaked-token"])
        assert _select_accept_subprotocol(ws) is None

    def test_returns_none_when_no_subprotocols(self):
        """웹 쿠키 흐름 — Sec-WebSocket-Protocol 자체를 안 보내므로 응답에도 미포함."""
        ws = _make_ws()
        assert _select_accept_subprotocol(ws) is None


# ──────────────────────────────────────────────────────────────────
# _verify_jwt
# ──────────────────────────────────────────────────────────────────

class TestVerifyJwt:
    def test_returns_user_id_and_jti_from_payload(self):
        token = _make_token("USER_jwt", jti="jti-explicit")
        ws = _make_ws(cookie_token=token)

        result = _verify_jwt(ws)

        assert result == ("USER_jwt", "jti-explicit")

    def test_falls_back_to_token_prefix_when_jti_missing(self):
        """jti claim 이 없으면 raw token 앞 32자를 jti 로 사용 — SessionService 기록과 일관."""
        token = _make_token("USER_jwt")  # jti 없음
        ws = _make_ws(cookie_token=token)

        result = _verify_jwt(ws)

        assert result is not None
        user_id, token_jti = result
        assert user_id == "USER_jwt"
        assert token_jti == token[:32]

    def test_returns_none_when_no_token(self):
        ws = _make_ws()
        assert _verify_jwt(ws) is None

    def test_returns_none_when_token_expired(self):
        token = _make_token("USER_jwt", expires_in=timedelta(seconds=-10))
        ws = _make_ws(cookie_token=token)
        assert _verify_jwt(ws) is None

    def test_returns_none_when_signature_invalid(self):
        token = _make_token("USER_jwt", secret="wrong-secret")
        ws = _make_ws(cookie_token=token)
        assert _verify_jwt(ws) is None

    def test_returns_none_when_payload_has_no_user_id(self):
        token = _make_token(user_id=None)
        ws = _make_ws(cookie_token=token)
        assert _verify_jwt(ws) is None

    def test_accepts_token_via_app_subprotocol(self):
        """앱 흐름 — 쿠키 없이 `auth.<jwt>` subprotocol 만으로 인증."""
        token = _make_token("USER_app", jti="jti-app")
        ws = _make_ws(
            subprotocols=[SUBPROTOCOL_VERSION, f"{SUBPROTOCOL_AUTH_PREFIX}{token}"],
        )

        result = _verify_jwt(ws)

        assert result == ("USER_app", "jti-app")
