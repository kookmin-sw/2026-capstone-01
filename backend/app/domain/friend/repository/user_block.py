from typing import Optional
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, exists

from app.domain.friend.model.user_block import UserBlock
from app.domain.auth.model.user import User


# 차단 목록 페이지 크기
PAGE_SIZE = 30


class UserBlockRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    # ──────────────────── Create ────────────────────

    async def save(self, block: UserBlock) -> UserBlock:
        """차단 관계 저장"""
        self.session.add(block)
        await self.session.flush()
        return block


    # ──────────────────── Read (단건) ────────────────────

    async def find_by_id(self, block_id: str) -> Optional[UserBlock]:
        """block_id로 단건 조회"""
        return await self.session.get(UserBlock, block_id)


    async def find_by_pair(self, blocker_id: str, blocked_id: str) -> Optional[UserBlock]:
        """(blocker, blocked) 정방향 단건 조회"""
        stmt = select(UserBlock).where(
            UserBlock.blocker_id == blocker_id,
            UserBlock.blocked_id == blocked_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


    async def find_blocks_between(self, user_a_id: str, user_b_id: str) -> list[UserBlock]:
        """두 유저 간의 차단 관계 (방향 무관) 조회 — 최대 2 row"""
        stmt = select(UserBlock).where(
            or_(
                (UserBlock.blocker_id == user_a_id) & (UserBlock.blocked_id == user_b_id),
                (UserBlock.blocker_id == user_b_id) & (UserBlock.blocked_id == user_a_id),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    async def has_blocker_blocked(self, blocker_id: str, blocked_id: str) -> bool:
        """(blocker → blocked) 방향 차단 존재 여부"""
        stmt = select(
            exists().where(
                UserBlock.blocker_id == blocker_id,
                UserBlock.blocked_id == blocked_id,
            )
        )
        result = await self.session.execute(stmt)
        return bool(result.scalar())


    # ──────────────────── Read (목록 — 커서 페이지네이션) ────────────────────

    async def find_blocks_by_user(
        self,
        blocker_id: str,
        cursor: Optional[str] = None,
    ) -> list[UserBlock]:
        """내가 차단한 유저 목록 (최신순)"""
        stmt = (
            select(UserBlock)
            .options(joinedload(UserBlock.blocked).joinedload(User.detail))
            .where(UserBlock.blocker_id == blocker_id)
        )

        if cursor:
            cursor_sub = select(UserBlock.created_at).where(UserBlock.block_id == cursor).scalar_subquery()
            stmt = stmt.where(
                or_(
                    UserBlock.created_at < cursor_sub,
                    (UserBlock.created_at == cursor_sub) & (UserBlock.block_id < cursor),
                )
            )

        stmt = stmt.order_by(UserBlock.created_at.desc(), UserBlock.block_id.desc()).limit(PAGE_SIZE)
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())


    # ──────────────────── Delete ────────────────────

    async def delete(self, block: UserBlock) -> None:
        """차단 해제"""
        await self.session.delete(block)
