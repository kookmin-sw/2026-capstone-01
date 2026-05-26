from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from app.domain.tour.model.favorite_place import FavoritePlace


class FavoritePlaceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ──────────────────── Create ────────────────────

    async def save(self, favorite: FavoritePlace) -> FavoritePlace:
        self.session.add(favorite)
        await self.session.flush()
        return favorite

    # ──────────────────── Read ────────────────────

    async def find_by_user_and_place(self, user_id: str, place_id: str) -> Optional[FavoritePlace]:
        """특정 유저의 특정 장소 즐겨찾기 조회"""
        stmt = select(FavoritePlace).where(
            FavoritePlace.user_id == user_id,
            FavoritePlace.place_id == place_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


    async def find_all_by_user(self, user_id: str) -> list[FavoritePlace]:
        """유저의 즐겨찾기 목록 조회 (최신순)"""
        stmt = (
            select(FavoritePlace)
            .where(FavoritePlace.user_id == user_id)
            .order_by(FavoritePlace.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    async def find_place_ids_by_user(self, user_id: str) -> list[str]:
        """유저의 즐겨찾기 place_id 목록만 조회"""
        stmt = (
            select(FavoritePlace.place_id)
            .where(FavoritePlace.user_id == user_id)
            .order_by(FavoritePlace.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    async def count_by_user(self, user_id: str) -> int:
        """유저의 즐겨찾기 개수 조회"""
        stmt = (
            select(func.count())
            .select_from(FavoritePlace)
            .where(FavoritePlace.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()


    async def find_favorited_place_ids(self, user_id: str, place_ids: list[str]) -> set[str]:
        """주어진 place_id 목록 중 유저가 즐겨찾기한 것만 반환 (배치 조회)"""
        if not place_ids:
            return set()
        stmt = (
            select(FavoritePlace.place_id)
            .where(
                FavoritePlace.user_id == user_id,
                FavoritePlace.place_id.in_(place_ids),
            )
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    # ──────────────────── Delete ────────────────────

    async def delete_by_user_and_place(self, user_id: str, place_id: str) -> None:
        """특정 즐겨찾기 삭제"""
        stmt = delete(FavoritePlace).where(
            FavoritePlace.user_id == user_id,
            FavoritePlace.place_id == place_id,
        )
        await self.session.execute(stmt)
