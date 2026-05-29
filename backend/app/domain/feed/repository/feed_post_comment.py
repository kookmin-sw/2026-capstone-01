"""FeedPostComment 리포지토리.

모든 read 가 `joinedload(user).joinedload(detail)` 로 닉네임/프로필 단일 SELECT 합성 —
async lazy-load (MissingGreenlet) 회피 + N+1 차단.
삭제는 양쪽 FK CASCADE 가 처리.
"""
from typing import Optional
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from app.domain.feed.model.feed_post_comment import FeedPostComment
from app.domain.auth.model.user import User


# 모바일 한 화면에 fit. 피드 list 와 별개 (댓글은 더 많이 쌓임).
PAGE_SIZE = 20


class FeedPostCommentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    async def save(self, comment: FeedPostComment) -> FeedPostComment:
        """INSERT — PK / CHECK 위반은 그대로 propagate."""
        self.session.add(comment)
        await self.session.flush()
        return comment


    async def find_by_id(self, comment_id: str) -> Optional[FeedPostComment]:
        """PK 단건 + user/detail. delete 권한 검증 / create 직후 reload 양쪽 공용 — 단일 진입점 유지."""
        stmt = (
            select(FeedPostComment)
            .options(joinedload(FeedPostComment.user).joinedload(User.detail))
            .where(FeedPostComment.comment_id == comment_id)
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()


    async def count_by_post(self, post_id: str) -> int:
        """게시물 댓글 수."""
        stmt = select(func.count()).where(FeedPostComment.post_id == post_id)
        result = await self.session.execute(stmt)
        return result.scalar_one()


    async def find_by_post(
        self,
        *,
        post_id: str,
        cursor: Optional[str] = None,
    ) -> list[FeedPostComment]:
        """댓글 목록 — `(created_at DESC, comment_id DESC)` 튜플 비교 커서 페이지네이션.

        `unique()` 는 joinedload outer-join 결과 중복 제거 (uselist=False detail 라 1:1).
        """
        stmt = (
            select(FeedPostComment)
            .options(joinedload(FeedPostComment.user).joinedload(User.detail))
            .where(FeedPostComment.post_id == post_id)
        )

        if cursor is not None:
            cursor_sub = (
                select(FeedPostComment.created_at)
                .where(FeedPostComment.comment_id == cursor)
                .scalar_subquery()
            )
            stmt = stmt.where(
                or_(
                    FeedPostComment.created_at < cursor_sub,
                    (FeedPostComment.created_at == cursor_sub)
                    & (FeedPostComment.comment_id < cursor),
                )
            )

        stmt = (
            stmt.order_by(
                FeedPostComment.created_at.desc(),
                FeedPostComment.comment_id.desc(),
            )
            .limit(PAGE_SIZE)
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())


    async def delete(self, comment: FeedPostComment) -> None:
        await self.session.delete(comment)
