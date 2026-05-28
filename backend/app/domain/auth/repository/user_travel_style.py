from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.domain.auth.model.user_travel_style import UserTravelStyle


class UserTravelStyleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    async def find_by_user_id(self, user_id: str) -> List[UserTravelStyle]:
        stmt = select(UserTravelStyle).where(UserTravelStyle.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    async def save(self, style: UserTravelStyle) -> UserTravelStyle:
        self.session.add(style)
        await self.session.flush()
        return style


    async def save_all(self, styles: List[UserTravelStyle]) -> List[UserTravelStyle]:
        self.session.add_all(styles)
        await self.session.flush()
        return styles


    async def delete_by_user_id(self, user_id: str) -> None:
        stmt = delete(UserTravelStyle).where(UserTravelStyle.user_id == user_id)
        await self.session.execute(stmt)
