"""FeedPost 리포지토리

쿼리 전략:
    - 단일 컴파운드 인덱스 `(user_id, visibility, created_at, post_id)` 가 모든 조회 +
      페이지네이션 + count 를 커버 (모델 docstring 참조).
    - viewer 관계 (본인 / 친구 / 비친구 / 차단) 분기는 모두 service 가 결정해
      `visibilities` 부분집합으로 전달 — 본 리포지토리는 visibility 정책을 모름.
    - 커서 페이지네이션은 friend 도메인의 (`updated_at`, `friendship_id`) 튜플 비교 패턴을
      (`created_at`, `post_id`) 로 옮긴 것과 동일.
    - 좋아요/댓글 수는 **correlated scalar subquery** 로 단일 SELECT 에 합성 — N+1 회피.
      PG 가 `ix_feed_post_like_post_id` / `ix_feed_post_comment_post_created` 의 prefix=
      post_id 를 활용해 row-level 카운트를 인덱스 scan 으로 처리. LIMIT 30 의 페이지네이션
      범위 안에서만 평가되므로 비용 미미.
    - `delete_by_user_id` 는 두지 않음 — `users` FK ON DELETE CASCADE 가 자동 정리.
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, literal, exists

from app.domain.feed.model.feed_post import FeedPost, FeedVisibility
from app.domain.feed.model.feed_post_like import FeedPostLike
from app.domain.feed.model.feed_post_comment import FeedPostComment
from app.domain.feed.dto.feed_post import FeedPostWithCounts


# 피드 그리드 3열 × 10행. friend 도메인 PAGE_SIZE 와 동일.
PAGE_SIZE = 30


def _like_count_subquery():
    """게시물별 좋아요 수 — FeedPost row 단위로 correlated 평가."""
    return (
        select(func.count())
        .select_from(FeedPostLike)
        .where(FeedPostLike.post_id == FeedPost.post_id)
        .correlate(FeedPost)
        .scalar_subquery()
    )


def _comment_count_subquery():
    """게시물별 댓글 수 — 동일 correlated subquery 패턴."""
    return (
        select(func.count())
        .select_from(FeedPostComment)
        .where(FeedPostComment.post_id == FeedPost.post_id)
        .correlate(FeedPost)
        .scalar_subquery()
    )


def _is_liked_subquery(viewer_id: Optional[str]):
    """viewer 가 해당 게시물에 좋아요 눌렀는지 — bool.

    - `viewer_id is None` (인증 없는 호출 가정 미래 대비): SQL 측 `false` 상수로 단락 평가.
    - 그 외: `EXISTS (SELECT 1 FROM feed_post_like WHERE post_id=:p AND user_id=:v)` —
      `feed_post_like` 의 composite PK `(user_id, post_id)` 가 정확히 lookup 인덱스로 작동
      해 row 0/1 건 평가에서 즉시 종료. like_count(SUM) 보다 짧음.
    """
    if viewer_id is None:
        return literal(False).label("is_liked")
    return exists(
        select(1)
        .select_from(FeedPostLike)
        .where(
            FeedPostLike.post_id == FeedPost.post_id,
            FeedPostLike.user_id == viewer_id,
        )
        .correlate(FeedPost)
    ).label("is_liked")


class FeedPostRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    # ──────────────────── Create / Update ────────────────────

    async def save(self, post: FeedPost) -> FeedPost:
        """새 게시물 INSERT — post_id PK 충돌 시 IntegrityError 그대로 propagate."""
        self.session.add(post)
        await self.session.flush()
        return post


    async def update(self, post: FeedPost) -> FeedPost:
        """변경된 필드 flush — visibility / caption 변경 경로 전용.

        호출 측에서 attached post 의 필드를 직접 mutate 한 뒤 본 메서드를 호출한다
        (friend 도메인의 `FriendshipRepository.update` 와 동일 패턴).
        """
        await self.session.flush()
        return post


    # ──────────────────── Read (단건) ────────────────────

    async def find_by_post_id(
        self,
        post_id: str,
        viewer_id: Optional[str] = None,
    ) -> Optional[FeedPostWithCounts]:
        """post_id PK 단건 + 좋아요/댓글 수 + viewer 좋아요 여부 한 쿼리 일괄 조회.

        `_load_owned_post` (mutate / 단건 조회) 와 `access.load_viewable_post` (좋아요/댓글 access check) 가 공통 사용. 
        후자는 카운트 미사용이지만 (~ 0.5ms 오버헤드) 메서드 분화 회피 — 단일 진입점 일관성 우선.

        `viewer_id is None` 이면 is_liked 는 SQL 측 `false` 단락 평가 (extra row hit 없음).
        """
        like_count = _like_count_subquery()
        comment_count = _comment_count_subquery()
        is_liked = _is_liked_subquery(viewer_id)
        stmt = (
            select(
                FeedPost,
                like_count.label("like_count"),
                comment_count.label("comment_count"),
                is_liked,
            )
            .where(FeedPost.post_id == post_id)
        )
        result = await self.session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            return None
        return FeedPostWithCounts(
            post=row.FeedPost,
            like_count=row.like_count,
            comment_count=row.comment_count,
            is_liked=bool(row.is_liked),
        )


    # ──────────────────── Read (목록 — 커서 페이지네이션) ────────────────────

    async def find_by_owner(
        self,
        *,
        owner_id: str,
        visibilities: list[FeedVisibility],
        cursor: Optional[str] = None,
        limit: int = PAGE_SIZE,
        viewer_id: Optional[str] = None,
    ) -> list[FeedPostWithCounts]:
        """소유자 + visibility 부분집합 조건으로 limit 만큼 조회 + 카운트 합성.

        viewer 관계에 따라 service 가 `visibilities` 를 결정한다:
            - 본인     → [PRIVATE, FRIENDS, PUBLIC]
            - 친구     → [FRIENDS, PUBLIC]
            - 비친구   → [PUBLIC]
            - 차단 관계 → service 가 호출 자체를 막음 (본 메서드에는 도달하지 않음)

        정렬: `(created_at DESC, post_id DESC)` — 컴파운드 인덱스와 일치, reverse-scan.
        cursor 는 마지막 row 의 `post_id` — `friend.repository.friendship` 의
        scalar_subquery 패턴 그대로 `created_at` 을 한 번 lookup 해 튜플 비교.

        좋아요/댓글 수: correlated scalar subquery 2개로 같은 SELECT 에 합성. PG 가 LIMIT
        적용 후 row × 2 carry 만 평가 → 인덱스 scan 으로 처리. N+1 회피.

        `limit` 은 default PAGE_SIZE (커서 페이지네이션 일반 케이스). popup 처럼 고정 N
        개만 필요한 경우 호출측이 직접 지정 (예: 9 개).
        """
        if not visibilities:
            # 빈 list 면 IN ([]) 가 되어 쿼리 자체가 의미 없음. 즉시 빈 결과.
            return []

        like_count = _like_count_subquery()
        comment_count = _comment_count_subquery()
        is_liked = _is_liked_subquery(viewer_id)
        stmt = select(
            FeedPost,
            like_count.label("like_count"),
            comment_count.label("comment_count"),
            is_liked,
        ).where(
            FeedPost.user_id == owner_id,
            FeedPost.visibility.in_(visibilities),
        )

        if cursor is not None:
            # 커서 row 의 created_at 을 같은 쿼리에 scalar_subquery 로 인라인.
            # (created_at < cur) OR (created_at == cur AND post_id < cur_id) — 안정 페이지네이션.
            cursor_sub = (
                select(FeedPost.created_at)
                .where(FeedPost.post_id == cursor)
                .scalar_subquery()
            )
            stmt = stmt.where(
                or_(
                    FeedPost.created_at < cursor_sub,
                    (FeedPost.created_at == cursor_sub) & (FeedPost.post_id < cursor),
                )
            )

        stmt = (
            stmt.order_by(FeedPost.created_at.desc(), FeedPost.post_id.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [
            FeedPostWithCounts(
                post=row.FeedPost,
                like_count=row.like_count,
                comment_count=row.comment_count,
                is_liked=bool(row.is_liked),
            )
            for row in result.all()
        ]


    # ──────────────────── Delete ────────────────────

    async def delete(self, post: FeedPost) -> None:
        """단건 삭제 — service 가 권한 검증 + storage prefix 삭제 후 호출.

        `feed_post_like` / `feed_post_comment` 는 ORM cascade (`all, delete-orphan`) +
        DB-level FK CASCADE 양쪽으로 자동 정리.
        """
        await self.session.delete(post)
