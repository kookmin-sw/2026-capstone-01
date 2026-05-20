"""FeedPostLike 리포지토리 — composite PK `(user_id, post_id)`.

좋아요 목록은 `joinedload(user).joinedload(detail)` 로 프로필까지 단일 SELECT 일괄.
유저 탈퇴 / 게시물 삭제 시 양쪽 FK CASCADE 가 자동 정리.
"""
from typing import Optional
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from app.domain.feed.model.feed_post_like import FeedPostLike
from app.domain.feed.model.feed_post import FeedPost
from app.domain.auth.model.user import User


class FeedPostLikeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    async def save(self, like: FeedPostLike) -> FeedPostLike:
        """INSERT — composite PK 충돌은 IntegrityError 로 propagate."""
        self.session.add(like)
        await self.session.flush()
        return like


    async def find_by_user_and_post(
        self, user_id: str, post_id: str,
    ) -> Optional[FeedPostLike]:
        """composite PK lookup."""
        return await self.session.get(FeedPostLike, (user_id, post_id))


    async def count_by_post(self, post_id: str) -> int:
        """게시물 좋아요 수."""
        stmt = select(func.count()).where(FeedPostLike.post_id == post_id)
        result = await self.session.execute(stmt)
        return result.scalar_one()


    async def count_total_for_owner(self, owner_id: str) -> int:
        """owner 의 모든 게시물이 받은 좋아요 총 합 (마이페이지 stats).

        PRIVATE 게시물의 좋아요도 포함 — 본인 stats. dangling like 는 FK CASCADE 로 없음.
        """
        stmt = (
            select(func.count())
            .select_from(FeedPostLike)
            .join(FeedPost, FeedPostLike.post_id == FeedPost.post_id)
            .where(FeedPost.user_id == owner_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()


    async def find_with_user_by_post(self, post_id: str) -> list[FeedPostLike]:
        """좋아요 유저 + 프로필 단일 SELECT (N+1 회피). 최신순.

        MVP 는 페이지네이션 없이 일괄 — N 이 커지면 후속에 cursor 도입.
        탈퇴 user 는 FK CASCADE 로 like 자체가 삭제 — dangling 없음.
        """
        stmt = (
            select(FeedPostLike)
            .options(joinedload(FeedPostLike.user).joinedload(User.detail))
            .where(FeedPostLike.post_id == post_id)
            .order_by(FeedPostLike.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())


    async def delete_by_user_and_post(self, user_id: str, post_id: str) -> None:
        """bulk delete (load 없이 DELETE)."""
        stmt = delete(FeedPostLike).where(
            FeedPostLike.user_id == user_id,
            FeedPostLike.post_id == post_id,
        )
        await self.session.execute(stmt)
