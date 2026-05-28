from typing import Dict
from enum import Enum                                                                        
from dataclasses import dataclass

from app.config.setting import settings


class OAuthProvider(str, Enum):
    GOOGLE = "google"


@dataclass
class OAuthConfig:
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    redirect_uri: str
    scope: str


OAUTH_CONFIGS: Dict[OAuthProvider, OAuthConfig] = {
    OAuthProvider.GOOGLE: OAuthConfig(
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        userinfo_url="https://www.googleapis.com/oauth2/v2/userinfo",
        redirect_uri=f"{settings.OAUTH_REDIRECT_BASE_URL}/api/auth/login",
        scope="openid email profile"
    )
}


# 앱(Capacitor/네이티브) 전용 OAuth 설정. redirect_uri 만 다르고 나머지는 동일.
# Google Cloud Console 에 '{base}/api/auth/login/app/callback' 가 별도 redirect URI 로 등록되어 있어야 한다.
OAUTH_APP_CONFIGS: Dict[OAuthProvider, OAuthConfig] = {
    OAuthProvider.GOOGLE: OAuthConfig(
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        userinfo_url="https://www.googleapis.com/oauth2/v2/userinfo",
        redirect_uri=f"{settings.OAUTH_REDIRECT_BASE_URL}/api/auth/login/app",
        scope="openid email profile"
    )
}