from app.core.oauth.base import OAuthClient, OAuthUser
from app.config.oauth import OAuthConfig, OAuthProvider


class GoogleOAuthClient(OAuthClient):
    def __init__(self, config: OAuthConfig):
        super().__init__(config, OAuthProvider.GOOGLE)


    async def get_user_info(self, access_token: str) -> OAuthUser:
        response = await self.client.get(
            self.config.userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        response.raise_for_status()
        
        user_data = response.json()
        return OAuthUser(
            id=user_data["id"],
            provider=self.provider,
            email=user_data.get("email"),
            name=user_data.get("name"),
        )