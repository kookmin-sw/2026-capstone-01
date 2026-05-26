from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.domain.notification.model.fcm_token import FcmToken


class FcmTokenRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    async def save(self, fcm_token: FcmToken) -> FcmToken:
        """INSERT. UNIQUE(token) 충돌은 그대로 IntegrityError — service 가 사전 find_by_token 으로 회피."""
        self.session.add(fcm_token)
        await self.session.flush()
        return fcm_token


    async def find_by_token(self, token: str) -> Optional[FcmToken]:
        """UNIQUE 제약상 0/1 row."""
        stmt = select(FcmToken).where(FcmToken.token == token)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


    async def find_by_user_id(self, user_id: str) -> list[FcmToken]:
        stmt = select(FcmToken).where(FcmToken.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    async def find_by_user_ids(self, user_ids: list[str]) -> list[FcmToken]:
        """그룹방 fan-out bulk."""
        if not user_ids:
            return []
        stmt = select(FcmToken).where(FcmToken.user_id.in_(user_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    async def update(self, fcm_token: FcmToken) -> FcmToken:
        """변경 flush — service 가 owner 갱신 후 호출."""
        await self.session.flush()
        return fcm_token


    async def delete(self, fcm_token: FcmToken) -> None:
        await self.session.delete(fcm_token)


    async def delete_by_token(self, token: str) -> None:
        """fetch 없이 즉시 정리 — 명시적 unregister 또는 UNREGISTERED 응답 시."""
        stmt = delete(FcmToken).where(FcmToken.token == token)
        await self.session.execute(stmt)


    async def delete_by_tokens(self, tokens: list[str]) -> None:
        """multicast 후 만료 토큰 bulk 정리."""
        if not tokens:
            return
        stmt = delete(FcmToken).where(FcmToken.token.in_(tokens))
        await self.session.execute(stmt)
