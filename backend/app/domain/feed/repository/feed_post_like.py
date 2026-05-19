"""FeedPostLike 리포지토리 — composite PK `(user_id, post_id)`.

`tripmate_post_like` 패턴 + 좋아요 목록은 프로필까지 한 쿼리로 일괄 로드:
    - `find_by_user_and_post`  : 단건 조회 (composite PK lookup)
    - `count_by_post`          : 좋아요 수 (인덱스 prefix=post_id)
    - `find_with_user_by_post` : 누른 유저 + 프로필 (`feed_post_like ⨝ users ⨝
                                  user_detail_inform`) 단일 SELECT, 최신순
    - `delete_by_user_and_post`: 단건 삭제

`delete_by_user_id` / `delete_by_post_id` 는 두지 않음 — 양쪽 FK ON DELETE CASCADE 가
유저 탈퇴 / 게시물 삭제 시 자동 정리.
"""
from typing import Optional
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.domain.auth.model.user import User
from app.domain.feed.model.feed_post import FeedPost
from app.domain.feed.model.feed_post_like import FeedPostLike


class FeedPostLikeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    # ──────────────────── Create ────────────────────

    async def save(self, like: FeedPostLike) -> FeedPostLike:
        """좋아요 INSERT — composite PK 충돌 시 IntegrityError 그대로 propagate."""
        self.session.add(like)
        await self.session.flush()
        return like


    # ──────────────────── Read ────────────────────

    async def find_by_user_and_post(
        self, user_id: str, post_id: str,
    ) -> Optional[FeedPostLike]:
        """특정 유저의 특정 게시물 좋아요 단건 조회 — composite PK lookup."""
        return await self.session.get(FeedPostLike, (user_id, post_id))


    async def count_by_post(self, post_id: str) -> int:
        """게시물의 좋아요 수 — `ix_feed_post_like_post_id` prefix-scan."""
        stmt = select(func.count()).where(FeedPostLike.post_id == post_id)
        result = await self.session.execute(stmt)
        return result.scalar_one()


    async def count_total_for_owner(self, owner_id: str) -> int:
        """`owner_id` 의 모든 게시물이 받은 좋아요 총 합 — 마이페이지 stats 용.

        SQL: `SELECT COUNT(*) FROM feed_post_like l JOIN feed_post p ON l.post_id = p.post_id
              WHERE p.user_id = :owner`
        plan:
            1) `feed_post.(user_id, ...)` 컴파운드 인덱스로 owner 의 post_id 추출
            2) `ix_feed_post_like_post_id` 로 각 post_id 별 row 카운트 합산
        owner 가 visibility=PRIVATE 인 게시물에 받은 좋아요도 합산에 포함 — 본인 stats
        이므로 자기 데이터 전부 노출. 게시물 삭제 시 `feed_post_like` 가 FK CASCADE 로
        함께 정리되므로 dangling like 없음.
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
        """좋아요 누른 유저 + 프로필을 한 쿼리에 일괄 로드 (최신순).

        `joinedload(FeedPostLike.user).joinedload(User.detail)` 가 LEFT OUTER JOIN 으로
        `feed_post_like ⨝ users ⨝ user_detail_inform` 을 단일 SELECT 에 합성 → 별도 batch
        조회 (`find_by_ids_with_profile`) 라운드트립 불필요. like 목록 N건 ↔ DB hit 1회.

        `result.unique()` 는 joinedload 가 outer-join 결과 row 를 곱셈으로 펼치는 케이스의
        ORM 객체 중복 제거 — uselist=False 인 detail 관계라 사실상 1:1 이지만 SQLAlchemy
        joinedload 권장 패턴 (chat / friend 도메인 동일).

        탈퇴 user → FK CASCADE 로 like 자체가 삭제되므로 dangling row 없음. detail 결손
        (회원가입 미완료 등) 케이스만 service 단의 fallback 책임.
        MVP 는 페이지네이션 없이 일괄 반환 (좋아요 N 이 큰 경우 후속에 cursor 도입).
        """
        stmt = (
            select(FeedPostLike)
            .options(joinedload(FeedPostLike.user).joinedload(User.detail))
            .where(FeedPostLike.post_id == post_id)
            .order_by(FeedPostLike.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())


    # ──────────────────── Delete ────────────────────

    async def delete_by_user_and_post(self, user_id: str, post_id: str) -> None:
        """단건 삭제 — bulk delete statement (load 없이 직접 DELETE)."""
        stmt = delete(FeedPostLike).where(
            FeedPostLike.user_id == user_id,
            FeedPostLike.post_id == post_id,
        )
        await self.session.execute(stmt)
