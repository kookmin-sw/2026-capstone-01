"""LoginAuthMiddleware — JWT 추출 우선순위 + 실패 분기 단위 테스트.

이번에 cookie-only 였던 미들웨어가 ``X-Auth-Token`` 헤더 (앱 채널) 도 받도록 확장됐다.
헤더 우선 / 쿠키 fallback / 실패 시 4종 401 분기를 RDB 없이 ASGI 레벨에서 검증.

EXCLUDE_PATHS / EXCLUDE_PREFIXES 도 1 case 만 확인 — 클래스 상수라 회귀 시 즉시 표면화.
"""

import pytest
import jwt
from fastapi.testclient import TestClient
from fastapi import FastAPI, Request
from datetime import datetime, timedelta, timezone

from app.middleware.auth import LoginAuthMiddleware
from app.config.setting import settings


pytestmark = pytest.mark.unit


# ──────────────────────────────────────────────────────────────────
# 토큰 헬퍼
# ──────────────────────────────────────────────────────────────────

def _make_token(
    user_id: str | None = "USER_a",
    expires_in: timedelta = timedelta(hours=1),
    secret: str | None = None,
    algorithm: str | None = None,
) -> str:
    payload: dict = {
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + expires_in,
    }
    if user_id is not None:
        payload["user_id"] = user_id
    return jwt.encode(
        payload,
        secret or settings.USER_LOGIN_JWT_SECRET_KEY,
        algorithm=algorithm or settings.USER_LOGIN_JWT_ALGORITHM,
    )


# ──────────────────────────────────────────────────────────────────
# 최소 ASGI 앱 — 미들웨어만 부착하고 보호 라우트 하나만 둔다
# ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(LoginAuthMiddleware)

    @app.get("/protected")
    async def protected(request: Request):
        # 미들웨어가 통과시키면 user_id 가 request.state 에 심어진다
        return {"user_id": request.state.user_id}

    @app.get("/health")
    async def health():  # EXCLUDE_PATHS 검증용
        return {"ok": True}

    @app.get("/api/auth/login/anything")
    async def login_like():  # EXCLUDE_PREFIXES (`/api/auth/login`) 검증용
        return {"ok": True}

    with TestClient(app) as c:
        yield c


# ──────────────────────────────────────────────────────────────────
# 성공 경로
# ──────────────────────────────────────────────────────────────────

class TestTokenSources:
    def test_accepts_x_auth_token_header(self, client):
        token = _make_token("USER_app")

        resp = client.get("/protected", headers={"X-Auth-Token": token})

        assert resp.status_code == 200
        assert resp.json() == {"user_id": "USER_app"}


    def test_accepts_cookie(self, client):
        token = _make_token("USER_web")
        client.cookies.set(settings.USER_LOGIN_COOKIE_NAME, token)

        resp = client.get("/protected")

        assert resp.status_code == 200
        assert resp.json() == {"user_id": "USER_web"}


    def test_header_wins_when_both_present(self, client):
        """헤더 → 쿠키 우선순위 — stale 쿠키가 살아 있어도 앱은 헤더로 정확한 user 를 본다."""
        header_token = _make_token("USER_from_header")
        cookie_token = _make_token("USER_from_cookie")
        client.cookies.set(settings.USER_LOGIN_COOKIE_NAME, cookie_token)

        resp = client.get("/protected", headers={"X-Auth-Token": header_token})

        assert resp.status_code == 200
        assert resp.json() == {"user_id": "USER_from_header"}


# ──────────────────────────────────────────────────────────────────
# 실패 분기 — login_missing / login_no_user_id / login_expired / login_invalid
# ──────────────────────────────────────────────────────────────────

class TestFailureBranches:
    def test_returns_401_when_no_token_anywhere(self, client):
        resp = client.get("/protected")

        assert resp.status_code == 401
        assert resp.json()["detail"] == "로그인이 필요합니다."


    def test_returns_401_when_token_has_no_user_id(self, client):
        token = _make_token(user_id=None)  # payload 에 user_id 누락

        resp = client.get("/protected", headers={"X-Auth-Token": token})

        assert resp.status_code == 401
        assert "유효하지 않은" in resp.json()["detail"]


    def test_returns_401_when_token_expired(self, client):
        expired = _make_token("USER_x", expires_in=timedelta(seconds=-10))

        resp = client.get("/protected", headers={"X-Auth-Token": expired})

        assert resp.status_code == 401
        assert "만료" in resp.json()["detail"]


    def test_returns_401_when_signature_invalid(self, client):
        token = _make_token("USER_x", secret="not-the-real-secret")

        resp = client.get("/protected", headers={"X-Auth-Token": token})

        assert resp.status_code == 401
        assert "유효하지 않은" in resp.json()["detail"]


    def test_returns_401_on_garbage_token(self, client):
        resp = client.get("/protected", headers={"X-Auth-Token": "not-a-jwt"})

        assert resp.status_code == 401
        assert "유효하지 않은" in resp.json()["detail"]


# ──────────────────────────────────────────────────────────────────
# 인증 우회 경로 — EXCLUDE_PATHS / EXCLUDE_PREFIXES
# ──────────────────────────────────────────────────────────────────

class TestExcludedPaths:
    def test_health_bypasses_auth(self, client):
        """EXCLUDE_PATHS 정확 매칭 — 토큰 없이도 200."""
        resp = client.get("/health")
        assert resp.status_code == 200


    def test_login_prefix_bypasses_auth(self, client):
        """EXCLUDE_PREFIXES `/api/auth/login` 이 `/app`, `/app/callback` 까지 자동 커버."""
        resp = client.get("/api/auth/login/anything")
        assert resp.status_code == 200
