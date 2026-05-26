from typing import Dict, Type

from app.core.oauth.google import GoogleOAuthClient
from app.core.oauth.base import OAuthClient
from app.config.oauth import OAuthProvider


# provider → client 클래스 매핑. web/app 로그인 라우터가 공유한다.
# provider 추가 시 본 dict 와 config/oauth.py 의 OAUTH_CONFIGS / OAUTH_APP_CONFIGS 모두 갱신해야 한다.
OAUTH_CLIENTS: Dict[OAuthProvider, Type[OAuthClient]] = {
    OAuthProvider.GOOGLE: GoogleOAuthClient,
}
