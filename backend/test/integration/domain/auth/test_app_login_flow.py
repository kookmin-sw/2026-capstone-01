"""앱 OAuth 로그인 라우터 HTTP 계약 테스트.

- GET /api/auth/login/app           — provider 인증 URL 로 307 redirect
- GET /api/auth/login/app/callback  — OAuth 코드 교환 → JWT 발급 → 딥링크로 307 redirect

OAuth provider 호출은 fake client 로, SignupService 도 mock 으로 격리한다. RDB / Mongo
가 필요 없으므로 ``POSTGRES_TEST_URL`` 미설정 환경에서도 동작.

웹 흐름(login.py) 과 동일한 구조를 신규 앱 흐름이 그대로 따라가는지를 검증하는 것이
이 파일의 핵심 목적이다 — state 파싱, deep link 형식, JWT payload, status 분기.
"""

from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.database.model  # noqa: F401 — 매퍼 선 등록 (dto 가 enum 참조)
from app.config.oauth import OAuthProvider
from app.config.setting import settings
from app.container import Container
from app.core.oauth import OAUTH_CLIENTS
from app.core.oauth.base import OAuthClient, OAuthUser
from app.domain.auth.dto.signup import SignupResult, SignupStatus
from app.domain.auth.router.app_login import APP_DEEP_LINK, router as app_login_router


pytestmark = pytest.mark.integration


# ──────────────────────────────────────────────────────────────────
# Fake OAuth client — 외부 HTTP 호출 차단
# ──────────────────────────────────────────────────────────────────

class _FakeGoogleClient(OAuthClient):
    """OAuth provider 호출을 격리하는 fake client.

    ``get_authorization_url`` 은 부모(순수 URL 빌더) 구현을 그대로 쓰고,
    토큰/유저정보 호출만 stub. 실 Google 엔드포인트에 접속하지 않는다.
    """

    USER_ID = "fake_google_uid"
    USER_EMAIL = "fake@example.com"
    USER_NAME = "Fake User"

    def __init__(self, config):
        super().__init__(config, OAuthProvider.GOOGLE)

    async def get_access_token(self, code: str, user_type: str) -> str:
        return f"fake-access-token:{code}"

    async def get_user_info(self, access_token: str) -> OAuthUser:
        return OAuthUser(
            id=self.USER_ID,
            provider=OAuthProvider.GOOGLE,
            email=self.USER_EMAIL,
            name=self.USER_NAME,
        )


# ──────────────────────────────────────────────────────────────────
# 공통 fixture
# ──────────────────────────────────────────────────────────────────

@pytest.fixture
def app_http(monkeypatch):
    """SignupService mock + GoogleOAuthClient stub 으로 최소 FastAPI 앱 + TestClient.

    ``OAUTH_CLIENTS`` 는 모듈 싱글톤 dict — ``monkeypatch.setitem`` 으로 GOOGLE 항목을
    fake 로 치환하면 라우터가 ``OAUTH_CLIENTS.get(type)`` 으로 받아오는 클래스가 자동 교체.
    """
    monkeypatch.setitem(OAUTH_CLIENTS, OAuthProvider.GOOGLE, _FakeGoogleClient)

    container = Container()
    signup_mock = AsyncMock()
    container.signup_service.override(providers.Object(signup_mock))

    app = FastAPI()
    app.container = container
    app.include_router(app_login_router, prefix="/api/auth")

    container.wire(modules=["app.domain.auth.router.app_login"])

    try:
        with TestClient(app) as client:
            yield client, signup_mock
    finally:
        container.unwire()


def _decode_utk(token: str) -> dict:
    return jwt.decode(
        token,
        settings.USER_LOGIN_JWT_SECRET_KEY,
        algorithms=[settings.USER_LOGIN_JWT_ALGORITHM],
    )


# ──────────────────────────────────────────────────────────────────
# GET /api/auth/login/app — 인증 URL redirect
# ──────────────────────────────────────────────────────────────────

class TestAppLoginRedirect:
    """provider 인증 페이지로의 redirect 가 웹 흐름과 동등하게 구성되는지 검증."""

    def test_redirects_to_google_with_app_state_and_app_redirect_uri(self, app_http):
        client, _ = app_http

        resp = client.get(
            "/api/auth/login/app",
            params={"type": "google"},
            follow_redirects=False,
        )

        assert resp.status_code == 307
        url = urlparse(resp.headers["location"])
        assert url.netloc == "accounts.google.com"

        params = parse_qs(url.query)
        # state 는 콜백에서 provider 추출 키 — `app:` prefix 가 웹의 `local:` / `server:` 와 분리됨.
        assert params["state"] == ["app:google"]
        # redirect_uri 는 앱 전용 경로 (`/api/auth/login/app/callback`) — 웹 redirect 와 분리.
        expected = f"{settings.OAUTH_REDIRECT_BASE_URL}/api/auth/login/app/callback"
        assert params["redirect_uri"] == [expected]
        # Google 은 `select_account` 강제 (base 클래스 분기) — 캐시된 세션 자동 로그인 방지.
        assert params["prompt"] == ["select_account"]

    def test_returns_422_when_provider_is_unknown(self, app_http):
        """OAuthProvider enum 에 없는 값은 FastAPI Query 검증 단계에서 422."""
        client, _ = app_http

        resp = client.get(
            "/api/auth/login/app",
            params={"type": "kakao"},
            follow_redirects=False,
        )

        assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────────
# GET /api/auth/login/app/callback — JWT 발급 + 딥링크
# ──────────────────────────────────────────────────────────────────

class TestAppLoginCallbackSuccess:
    """정상 콜백 — signup status 에 따라 딥링크 query 가 분기되는지 검증."""

    def test_redirects_to_deep_link_with_jwt_in_utk_query(self, app_http):
        client, signup_mock = app_http
        signup_mock.check_and_register.return_value = SignupResult(
            user_id="USER_app_1", status=SignupStatus.NEW,
        )

        resp = client.get(
            "/api/auth/login/app/callback",
            params={"code": "auth_code_xyz", "state": "app:google"},
            follow_redirects=False,
        )

        assert resp.status_code == 307
        url = urlparse(resp.headers["location"])
        # 딥링크 — 안드/iOS 가 앱으로 복귀시키는 custom scheme
        assert f"{url.scheme}://{url.netloc}{url.path}" == APP_DEEP_LINK

        params = parse_qs(url.query)
        assert params["status"] == ["new"]
        assert params["email"] == [_FakeGoogleClient.USER_EMAIL]
        assert params["name"] == [_FakeGoogleClient.USER_NAME]

        # utk 는 보호 경로 진입 시 앱이 X-Auth-Token 헤더로 다시 보낼 raw JWT
        decoded = _decode_utk(params["utk"][0])
        assert decoded["user_id"] == "USER_app_1"
        assert "exp" in decoded and "iat" in decoded

        # signup_service 호출 인자 검증 — provider value + provider_id 둘 다 전달
        signup_mock.check_and_register.assert_awaited_once_with(
            auth_provider=OAuthProvider.GOOGLE.value,
            auth_provider_id=_FakeGoogleClient.USER_ID,
        )

    def test_still_issues_token_on_withdrawal_pending(self, app_http):
        """탈퇴 유예 유저도 토큰을 발급한다 — 프론트가 status 로 cancel 화면 라우팅.

        보호 경로 진입 시 RegisterCheck 미들웨어가 419 로 차단하므로 보안상 안전 (web 과 동일 정책).
        """
        client, signup_mock = app_http
        signup_mock.check_and_register.return_value = SignupResult(
            user_id="USER_pending", status=SignupStatus.WITHDRAWAL_PENDING,
        )

        resp = client.get(
            "/api/auth/login/app/callback",
            params={"code": "c1", "state": "app:google"},
            follow_redirects=False,
        )

        assert resp.status_code == 307
        params = parse_qs(urlparse(resp.headers["location"]).query)
        assert params["status"] == ["withdrawal_pending"]
        # 토큰은 발급되어야 한다 (프론트가 cancel 흐름에서 사용)
        assert _decode_utk(params["utk"][0])["user_id"] == "USER_pending"

    def test_omits_optional_user_fields_when_provider_returns_none(self, app_http, monkeypatch):
        """provider 가 email/name 을 안 주는 경우 query 에 키 자체가 빠진다 (빈 문자열 X)."""

        class _BareGoogleClient(_FakeGoogleClient):
            async def get_user_info(self, access_token: str) -> OAuthUser:
                return OAuthUser(
                    id=self.USER_ID, provider=OAuthProvider.GOOGLE,
                    email=None, name=None,
                )

        monkeypatch.setitem(OAUTH_CLIENTS, OAuthProvider.GOOGLE, _BareGoogleClient)

        client, signup_mock = app_http
        signup_mock.check_and_register.return_value = SignupResult(
            user_id="USER_bare", status=SignupStatus.COMPLETE,
        )

        resp = client.get(
            "/api/auth/login/app/callback",
            params={"code": "c", "state": "app:google"},
            follow_redirects=False,
        )

        params = parse_qs(urlparse(resp.headers["location"]).query)
        assert "email" not in params
        assert "name" not in params
        assert params["status"] == ["complete"]
        assert params["utk"]  # 토큰은 무조건 발급


class TestAppLoginCallbackErrors:
    """잘못된 state / 미지원 provider — 400."""

    def test_returns_400_when_state_has_no_colon(self, app_http):
        client, signup_mock = app_http

        resp = client.get(
            "/api/auth/login/app/callback",
            params={"code": "c", "state": "garbage_no_colon"},
            follow_redirects=False,
        )

        assert resp.status_code == 400
        assert "state" in resp.json()["detail"]
        signup_mock.check_and_register.assert_not_called()

    def test_returns_400_when_state_provider_unknown(self, app_http):
        client, signup_mock = app_http

        resp = client.get(
            "/api/auth/login/app/callback",
            params={"code": "c", "state": "app:facebook"},
            follow_redirects=False,
        )

        assert resp.status_code == 400
        assert "OAuth" in resp.json()["detail"]
        signup_mock.check_and_register.assert_not_called()
