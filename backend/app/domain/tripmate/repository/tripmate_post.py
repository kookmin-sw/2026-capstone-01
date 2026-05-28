from typing import Optional
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, case, literal, exists

from app.domain.tripmate.model.tripmate_post_like import TripmatePostLike
from app.domain.tripmate.model.tripmate_post import TripmatePost
from app.domain.auth.model.user_detail_inform import UserDetailInform
from app.domain.auth.model.user import User


# 게시글 조회 개수
PAGE_SIZE = 30


class TripmatePostRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    # ──────────────────── Create ────────────────────

    async def save(self, post: TripmatePost) -> TripmatePost:
        self.session.add(post)
        await self.session.flush()
        return post


    # ──────────────────── Read (단건) ────────────────────

    async def find_by_id(self, post_id: str) -> Optional[TripmatePost]:
        """게시글 단건 조회 (게시글 데이터만, 수정/삭제 시 검증용)"""
        return await self.session.get(TripmatePost, post_id)


    async def find_by_id_with_detail(self, post_id: str, user_id: Optional[str] = None) -> Optional[TripmatePost]:
        """게시글 단건 조회 (이미지 + 좋아요 수 + is_liked 포함, 상세 조회용임 display 없는 거 주의)"""
        stmt = (
            select(
                TripmatePost,
                func.count(func.distinct(TripmatePostLike.user_id)).label("like_count"),
                func.max(case(
                    (TripmatePostLike.user_id == user_id, literal(1)),
                    else_=literal(0),
                )).label("is_liked") if user_id else literal(0).label("is_liked"),
            )
            .outerjoin(TripmatePostLike, TripmatePost.post_id == TripmatePostLike.post_id)
            .options(
                joinedload(TripmatePost.images),
                joinedload(TripmatePost.user).joinedload(User.detail),
            )
            .where(TripmatePost.post_id == post_id)
            .group_by(TripmatePost.post_id)
        )
        result = await self.session.execute(stmt)
        row = result.unique().first()
        if row is None:
            return None

        post = row[0]
        post.like_count = row[1]
        post.is_liked = bool(row[2])
        return post


    # ──────────────────── Read (목록 — 커서 기반 페이지네이션) ────────────────────

    async def find_all_displayed(self, cursor: Optional[str] = None, user_id: Optional[str] = None) -> list[TripmatePost]:
        """최신순 30개 조회, cursor(post_id) 이후부터 다음 페이지"""
        stmt = (
            select(
                TripmatePost,
                func.count(func.distinct(TripmatePostLike.user_id)).label("like_count"),
                func.max(case(
                    (TripmatePostLike.user_id == user_id, literal(1)),
                    else_=literal(0),
                )).label("is_liked") if user_id else literal(0).label("is_liked"),
            )
            .outerjoin(TripmatePostLike, TripmatePost.post_id == TripmatePostLike.post_id)
            .options(
                joinedload(TripmatePost.images),
                joinedload(TripmatePost.user).joinedload(User.detail),
            )
            .where(TripmatePost.is_displayed == True)
        )

        if cursor:
            # cursor로 받은 post_id의 created_at 기준으로 다음 페이지
            cursor_sub = select(TripmatePost.created_at).where(TripmatePost.post_id == cursor).scalar_subquery()
            stmt = stmt.where(
                or_(
                    TripmatePost.created_at < cursor_sub,
                    (TripmatePost.created_at == cursor_sub) & (TripmatePost.post_id < cursor),
                )
            )

        stmt = (
            stmt
            .group_by(TripmatePost.post_id)
            .order_by(TripmatePost.created_at.desc(), TripmatePost.post_id.desc())
            .limit(PAGE_SIZE)
        )

        result = await self.session.execute(stmt)
        rows = result.unique().all()
        return self._attach_extras(rows)


    # ──────────────────── Read (검색) ────────────────────

    async def search(
        self,
        keyword: str,
        cursor: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> list[TripmatePost]:
        """제목, 내용, 작성자 닉네임으로 검색 (최신순, 커서 페이지네이션)"""
        escaped = keyword.replace("%", "\\%").replace("_", "\\_")
        like_pattern = f"%{escaped}%"

        stmt = (
            select(
                TripmatePost,
                func.count(func.distinct(TripmatePostLike.user_id)).label("like_count"),
                func.max(case(
                    (TripmatePostLike.user_id == user_id, literal(1)),
                    else_=literal(0),
                )).label("is_liked") if user_id else literal(0).label("is_liked"),
            )
            .outerjoin(TripmatePostLike, TripmatePost.post_id == TripmatePostLike.post_id)
            .options(
                joinedload(TripmatePost.images),
                joinedload(TripmatePost.user).joinedload(User.detail),
            )
            .where(
                TripmatePost.is_displayed == True,
                or_(
                    TripmatePost.title.ilike(like_pattern),
                    TripmatePost.content.ilike(like_pattern),
                    exists(
                        select(UserDetailInform.user_id).where(
                            UserDetailInform.user_id == TripmatePost.user_id,
                            UserDetailInform.user_name.ilike(like_pattern),
                        )
                    ),
                ),
            )
        )

        if cursor:
            cursor_sub = select(TripmatePost.created_at).where(TripmatePost.post_id == cursor).scalar_subquery()
            stmt = stmt.where(
                or_(
                    TripmatePost.created_at < cursor_sub,
                    (TripmatePost.created_at == cursor_sub) & (TripmatePost.post_id < cursor),
                )
            )

        stmt = (
            stmt
            .group_by(TripmatePost.post_id)
            .order_by(TripmatePost.created_at.desc(), TripmatePost.post_id.desc())
            .limit(PAGE_SIZE)
        )

        result = await self.session.execute(stmt)
        rows = result.unique().all()
        return self._attach_extras(rows)


    # ──────────────────── Update ────────────────────

    async def update(self, post: TripmatePost) -> TripmatePost:
        await self.session.flush()
        return post


    # ──────────────────── Delete ────────────────────

    async def delete(self, post: TripmatePost) -> None:
        await self.session.delete(post)


    # ──────────────────── 내부 유틸 ────────────────────

    @staticmethod
    def _attach_extras(rows) -> list[TripmatePost]:
        """쿼리 결과 Row에서 like_count, is_liked를 Post 객체에 부착"""
        posts = []
        for row in rows:
            post = row[0]
            post.like_count = row[1]
            post.is_liked = bool(row[2])
            posts.append(post)
        return posts
