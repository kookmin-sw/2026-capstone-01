from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domain.auth.model.user_detail_inform import UserDetailInform


class UserDetailInformRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    async def find_by_user_id(self, user_id: str) -> Optional[UserDetailInform]:
        return await self.session.get(UserDetailInform, user_id)


    async def find_by_email(self, email: str) -> Optional[UserDetailInform]:
        stmt = select(UserDetailInform).where(UserDetailInform.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


    async def save(self, detail: UserDetailInform) -> UserDetailInform:
        self.session.add(detail)
        await self.session.flush()
        return detail


    async def update(self, detail: UserDetailInform) -> UserDetailInform:
        merged = await self.session.merge(detail)
        await self.session.flush()
        return merged


    async def delete(self, detail: UserDetailInform) -> None:
        await self.session.delete(detail)
