"""FeedPostComment 리포지토리 — `(post_id, created_at)` 컴파운드 인덱스 활용.

쿼리 전략:
    - 단일 인덱스 `ix_feed_post_comment_post_created` 가 게시물별 시간순 조회 / 페이지네이션
      / count 모두 커버.
    - 정렬은 DESC (최신순) — 피드 list 와 일관. 인덱스 reverse-scan.
    - 커서 페이지네이션은 friend / feed_post 패턴 그대로 `(created_at, comment_id)` 튜플 비교.
    - 모든 read 메서드 (`find_by_id` / `find_by_post`) 가 `joinedload(FeedPostComment.user)
      .joinedload(User.detail)` 로 LEFT OUTER JOIN — `feed_post_comment ⨝ users ⨝
      user_detail_inform` 단일 SELECT. 단건/목록 모두 응답 단계에서 추가 lazy-load 없이
      닉네임/프로필 이미지 채우기 가능. async 환경에서 relationship lazy-load 는 막혀 있어
      explicit join 이 필수.
    - delete cascade 는 `users` / `feed_post` FK ON DELETE CASCADE 가 처리 — 본 리포지토리는
      단건 삭제만.
"""
from typing import Optional
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from app.domain.feed.model.feed_post_comment import FeedPostComment
from app.domain.auth.model.user import User


# 댓글 페이지 크기 — 모바일 한 화면에 fit. 피드 list 와 다른 값 (댓글은 더 짧고 많이 쌓임).
PAGE_SIZE = 20


class FeedPostCommentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    # ──────────────────── Create ────────────────────

    async def save(self, comment: FeedPostComment) -> FeedPostComment:
        """댓글 INSERT — comment_id PK / CHECK(content) 위반은 그대로 propagate."""
        self.session.add(comment)
        await self.session.flush()
        return comment


    # ──────────────────── Read (단건) ────────────────────

    async def find_by_id(self, comment_id: str) -> Optional[FeedPostComment]:
        """comment_id PK 단건 + user/detail 한 쿼리 일괄 조회.

        delete 권한 검증 / create 직후 응답 reload 양쪽에 사용 — 단일 SELECT 로 user.detail
        까지 로드해 후속 lazy-load 없이 DTO 변환 가능. delete 시점에는 user.detail 이 불필요
        하지만 (~0.3ms 오버헤드) 메서드 분화 회피로 호출처 일관성 유지.

        `session.get(...)` 대신 `select + joinedload` 로 변경 — primary key lookup 에 LEFT
        OUTER JOIN 1회 추가, PG 가 nested loop 으로 효율 처리.
        """
        stmt = (
            select(FeedPostComment)
            .options(joinedload(FeedPostComment.user).joinedload(User.detail))
            .where(FeedPostComment.comment_id == comment_id)
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()


    async def count_by_post(self, post_id: str) -> int:
        """게시물 댓글 수 — 인덱스 prefix=post_id 로 효율적."""
        stmt = select(func.count()).where(FeedPostComment.post_id == post_id)
        result = await self.session.execute(stmt)
        return result.scalar_one()


    # ──────────────────── Read (목록 — 커서 페이지네이션) ────────────────────

    async def find_by_post(
        self,
        *,
        post_id: str,
        cursor: Optional[str] = None,
    ) -> list[FeedPostComment]:
        """게시물 댓글 목록 — 최신순 PAGE_SIZE 만큼 + 작성자 프로필 일괄 로드.

        정렬: `(created_at DESC, comment_id DESC)` — 인덱스 reverse-scan.
        cursor 는 마지막 row 의 `comment_id` — `feed_post.find_by_owner` 와 동일 패턴
        (scalar_subquery 로 created_at 인라인 lookup + 튜플 비교).

        `joinedload(FeedPostComment.user).joinedload(User.detail)` 로 `feed_post_comment ⨝
        users ⨝ user_detail_inform` 을 단일 SELECT 합성 → N+1 / batch 라운드트립 회피.
        `result.unique()` 는 joinedload 표준 패턴 (uselist=False detail 라 사실상 1:1).
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


    # ──────────────────── Delete ────────────────────

    async def delete(self, comment: FeedPostComment) -> None:
        """단건 삭제 — service 가 작성자 검증 후 호출."""
        await self.session.delete(comment)
