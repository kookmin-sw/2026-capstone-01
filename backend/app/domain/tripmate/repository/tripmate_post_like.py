from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from app.domain.tripmate.model.tripmate_post_like import TripmatePostLike


class TripmatePostLikeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    # ──────────────────── Create ────────────────────

    async def save(self, like: TripmatePostLike) -> TripmatePostLike:
        """좋아요 추가"""
        self.session.add(like)
        await self.session.flush()
        return like


    # ──────────────────── Read ────────────────────

    async def find_by_user_and_post(self, user_id: str, post_id: str) -> Optional[TripmatePostLike]:
        """특정 유저가 특정 게시글에 좋아요를 눌렀는지 조회"""
        return await self.session.get(TripmatePostLike, (user_id, post_id))


    async def find_user_ids_by_post(self, post_id: str) -> list[str]:
        """게시글에 좋아요 누른 유저 ID 목록 조회 (최신순)"""
        stmt = (
            select(TripmatePostLike.user_id)
            .where(TripmatePostLike.post_id == post_id)
            .order_by(TripmatePostLike.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    async def count_by_post(self, post_id: str) -> int:
        """게시글의 좋아요 수 조회"""
        stmt = select(func.count()).where(TripmatePostLike.post_id == post_id)
        result = await self.session.execute(stmt)
        return result.scalar_one()


    # ──────────────────── Delete ────────────────────

    async def delete_by_user_and_post(self, user_id: str, post_id: str) -> None:
        """유저 ID + 게시글 ID로 좋아요 취소"""
        stmt = (
            delete(TripmatePostLike)
            .where(
                TripmatePostLike.user_id == user_id,
                TripmatePostLike.post_id == post_id,
            )
        )
        await self.session.execute(stmt)
