from typing import Optional
from sqlalchemy.orm import contains_eager, selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.domain.friend.model.user_block import UserBlock
from app.domain.auth.model.user_detail_inform import UserDetailInform
from app.domain.auth.model.user import User, UserStatus


# 검색 결과 페이지 크기
PAGE_SIZE = 30


class FriendSearchRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    # ──────────────────── Read (검색 — 커서 페이지네이션) ────────────────────

    async def search_active_users(
        self,
        viewer_id: str,
        keyword: str,
        cursor: Optional[str] = None,
    ) -> list[User]:
        """`viewer_id` 기준 친구 추가 후보 ACTIVE 유저 검색.

        - 매칭: `user_id` 또는 `user_detail_inform.user_name` 부분일치 (ILIKE)
        - 본인 / 내가 차단 / 나를 차단한 유저 제외
        - 정렬: 가입 최신순 (created_at DESC, user_id DESC)
        - detail 미존재(2차 회원가입 미완료) 유저는 INNER JOIN 으로 자연 제외
          — 검색 결과는 `user_name` 표시가 필수이므로 detail 없는 유저는 노출 X
        - detail (1:1) 은 필터용 join 을 그대로 재사용해 `contains_eager` 로 로드
          → user_detail_inform 으로의 join 은 1번만 발생
        - travel_styles 는 1:N 이라 joinedload + LIMIT 의 cardinality 충돌을 피해
          `selectinload` 로 별도 IN 쿼리 로드
        """
        escaped = keyword.replace("%", "\\%").replace("_", "\\_")
        like_pattern = f"%{escaped}%"

        blocked_by_me = (
            select(UserBlock.blocked_id).where(UserBlock.blocker_id == viewer_id)
        )
        blocked_me = (
            select(UserBlock.blocker_id).where(UserBlock.blocked_id == viewer_id)
        )

        stmt = (
            select(User)
            .join(User.detail)
            .options(
                contains_eager(User.detail),
                selectinload(User.travel_styles),
            )
            .where(
                User.user_id != viewer_id,
                User.status == UserStatus.ACTIVE,
                User.user_id.notin_(blocked_by_me),
                User.user_id.notin_(blocked_me),
                or_(
                    User.user_id.ilike(like_pattern),
                    UserDetailInform.user_name.ilike(like_pattern),
                ),
            )
        )

        if cursor:
            cursor_sub = select(User.created_at).where(User.user_id == cursor).scalar_subquery()
            stmt = stmt.where(
                or_(
                    User.created_at < cursor_sub,
                    (User.created_at == cursor_sub) & (User.user_id < cursor),
                )
            )

        stmt = stmt.order_by(User.created_at.desc(), User.user_id.desc()).limit(PAGE_SIZE)
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())
