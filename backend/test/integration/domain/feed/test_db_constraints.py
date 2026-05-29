"""Feed 도메인의 DB-level 제약 검증 (M6 — 탈퇴 cascade).

Service 로직이 아닌 **schema 자체** (FK ON DELETE CASCADE / composite PK / CHECK
constraint) 가 실제로 동작하는지를 raw INSERT / DELETE 로 확인한다.

검증 매트릭스:

    | 이벤트                            | 기대 결과                              |
    |---|---|
    | user 삭제 (owner)                 | 본인 feed_post + 그 post 의 like/comment 정리 |
    | user 삭제 (liker, 타인 post)      | 해당 like 만 정리, post 보존              |
    | user 삭제 (commenter, 타인 post)  | 해당 comment 만 정리, post 보존           |
    | feed_post 삭제                    | 그 post 의 like + comment 정리           |
    | feed_post_like (user, post) 중복  | composite PK 위반 → IntegrityError      |
    | feed_post_comment.content 빈 문자열| CHECK 위반 → IntegrityError              |

`WithdrawService.purge` 자체의 회귀 가드는 auth 도메인 통합 테스트 영역. 본 모듈은
plan §2.2 의 "유저 탈퇴 → users 삭제 → FK CASCADE → feed_* 모두 정리" 흐름이 schema
레벨에서 보장됨을 검증 — service 단계 (hard_delete_by_id) 가 변경되어도 cascade 자체는
DB 가 책임진다는 약속의 안전망.

friend 도메인의 `test_db_constraints.py` 패턴 차용 (raw DELETE FROM users + 새 session
으로 검증).
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, text
import pytest

from app.domain.feed.model.feed_post_like import FeedPostLike
from app.domain.feed.model.feed_post_comment import FeedPostComment
from app.domain.feed.model.feed_post import FeedPost, FeedVisibility


pytestmark = pytest.mark.integration


# ──────────────────── helpers ────────────────────

def _mk_post(*, user_id: str, post_id: str = "FDP_it_x") -> FeedPost:
    """test 용 FeedPost — 모든 NOT NULL URL 필드를 dummy 로 채움."""
    return FeedPost(
        post_id=post_id,
        user_id=user_id,
        visibility=FeedVisibility.PUBLIC,
        caption=None,
        original_url="https://x/o.jpg",
        thumbnail_small_url="https://x/s.jpg",
        thumbnail_medium_url="https://x/m.jpg",
    )


# ──────────────────── user 삭제 → cascade ────────────────────

class TestUserDeleteCascadesOwnedFeed:
    """post owner 가 삭제되면 본인 feed_post + 그 post 에 매달린 like/comment 까지 정리."""

    async def test_owner_delete_cascades_feed_post(self, seed_users, session_factory):
        owner, _, _ = await seed_users(3)
        async with session_factory() as s:
            s.add(_mk_post(user_id=owner, post_id="FDP_it_a"))
            await s.commit()

        async with session_factory() as s:
            await s.execute(text("DELETE FROM users WHERE user_id = :uid"), {"uid": owner})
            await s.commit()

        async with session_factory() as s:
            rows = (await s.execute(select(FeedPost))).scalars().all()
        assert rows == []


    async def test_owner_delete_cascades_likes_on_own_post(
        self, seed_users, session_factory,
    ):
        """owner 삭제 → post cascade → 그 post 의 like 도 chained cascade."""
        owner, liker, _ = await seed_users(3)
        async with session_factory() as s:
            s.add(_mk_post(user_id=owner, post_id="FDP_it_a"))
            await s.commit()
        async with session_factory() as s:
            s.add(FeedPostLike(user_id=liker, post_id="FDP_it_a"))
            await s.commit()

        async with session_factory() as s:
            await s.execute(text("DELETE FROM users WHERE user_id = :uid"), {"uid": owner})
            await s.commit()

        async with session_factory() as s:
            rows = (await s.execute(select(FeedPostLike))).scalars().all()
        assert rows == []


    async def test_owner_delete_cascades_comments_on_own_post(
        self, seed_users, session_factory,
    ):
        owner, commenter, _ = await seed_users(3)
        async with session_factory() as s:
            s.add(_mk_post(user_id=owner, post_id="FDP_it_a"))
            await s.commit()
        async with session_factory() as s:
            s.add(FeedPostComment(
                comment_id="FDC_it_a", post_id="FDP_it_a",
                user_id=commenter, content="hi",
            ))
            await s.commit()

        async with session_factory() as s:
            await s.execute(text("DELETE FROM users WHERE user_id = :uid"), {"uid": owner})
            await s.commit()

        async with session_factory() as s:
            rows = (await s.execute(select(FeedPostComment))).scalars().all()
        assert rows == []


class TestUserDeleteCascadesActionsOnOthersPost:
    """liker / commenter 삭제 → 자기 like/comment 만 정리, post 자체는 보존 (다른 user 소유)."""

    async def test_liker_delete_cascades_only_own_like(
        self, seed_users, session_factory,
    ):
        owner, liker, bystander = await seed_users(3)
        async with session_factory() as s:
            s.add(_mk_post(user_id=owner, post_id="FDP_it_a"))
            await s.commit()
        async with session_factory() as s:
            # 두 명이 같은 post 에 좋아요
            s.add(FeedPostLike(user_id=liker, post_id="FDP_it_a"))
            s.add(FeedPostLike(user_id=bystander, post_id="FDP_it_a"))
            await s.commit()

        async with session_factory() as s:
            await s.execute(text("DELETE FROM users WHERE user_id = :uid"), {"uid": liker})
            await s.commit()

        async with session_factory() as s:
            # liker 의 like 만 사라지고 bystander 의 like + post 자체는 보존
            likes = (await s.execute(select(FeedPostLike))).scalars().all()
            posts = (await s.execute(select(FeedPost))).scalars().all()
        assert {l.user_id for l in likes} == {bystander}
        assert len(posts) == 1


    async def test_commenter_delete_cascades_only_own_comment(
        self, seed_users, session_factory,
    ):
        owner, commenter, bystander = await seed_users(3)
        async with session_factory() as s:
            s.add(_mk_post(user_id=owner, post_id="FDP_it_a"))
            await s.commit()
        async with session_factory() as s:
            s.add(FeedPostComment(
                comment_id="FDC_it_a", post_id="FDP_it_a",
                user_id=commenter, content="comment by user",
            ))
            s.add(FeedPostComment(
                comment_id="FDC_it_b", post_id="FDP_it_a",
                user_id=bystander, content="comment by bystander",
            ))
            await s.commit()

        async with session_factory() as s:
            await s.execute(text("DELETE FROM users WHERE user_id = :uid"), {"uid": commenter})
            await s.commit()

        async with session_factory() as s:
            comments = (await s.execute(select(FeedPostComment))).scalars().all()
            posts = (await s.execute(select(FeedPost))).scalars().all()
        assert {c.user_id for c in comments} == {bystander}
        assert len(posts) == 1


# ──────────────────── feed_post 삭제 → cascade ────────────────────

class TestFeedPostDeleteCascade:
    """게시물 삭제 → 그 post 의 like + comment 정리. (좋아요/댓글 작성자 user 는 보존.)"""

    async def test_post_delete_cascades_likes(self, seed_users, session_factory):
        owner, liker, _ = await seed_users(3)
        async with session_factory() as s:
            s.add(_mk_post(user_id=owner, post_id="FDP_it_a"))
            await s.commit()
        async with session_factory() as s:
            s.add(FeedPostLike(user_id=liker, post_id="FDP_it_a"))
            await s.commit()

        async with session_factory() as s:
            await s.execute(
                text("DELETE FROM feed_post WHERE post_id = :pid"), {"pid": "FDP_it_a"},
            )
            await s.commit()

        async with session_factory() as s:
            likes = (await s.execute(select(FeedPostLike))).scalars().all()
        assert likes == []


    async def test_post_delete_cascades_comments(self, seed_users, session_factory):
        owner, commenter, _ = await seed_users(3)
        async with session_factory() as s:
            s.add(_mk_post(user_id=owner, post_id="FDP_it_a"))
            await s.commit()
        async with session_factory() as s:
            s.add(FeedPostComment(
                comment_id="FDC_it_a", post_id="FDP_it_a",
                user_id=commenter, content="hi",
            ))
            await s.commit()

        async with session_factory() as s:
            await s.execute(
                text("DELETE FROM feed_post WHERE post_id = :pid"), {"pid": "FDP_it_a"},
            )
            await s.commit()

        async with session_factory() as s:
            comments = (await s.execute(select(FeedPostComment))).scalars().all()
        assert comments == []


# ──────────────────── PK / CHECK constraint ────────────────────

class TestLikeCompositePrimaryKey:
    """`feed_post_like(user_id, post_id)` composite PK — 같은 쌍 두 번 INSERT 거절."""

    async def test_duplicate_user_post_pair_rejected(self, seed_users, session_factory):
        owner, liker, _ = await seed_users(3)
        async with session_factory() as s:
            s.add(_mk_post(user_id=owner, post_id="FDP_it_a"))
            await s.commit()

        async with session_factory() as s:
            s.add(FeedPostLike(user_id=liker, post_id="FDP_it_a"))
            await s.commit()

        async with session_factory() as s:
            s.add(FeedPostLike(user_id=liker, post_id="FDP_it_a"))
            with pytest.raises(IntegrityError):
                await s.commit()


class TestCommentCheckConstraint:
    """`ck_feed_post_comment_min_length` — content 가 빈 문자열이면 거절.

    Service 의 `_normalize_content` 가 1차 방어선, schema 의 `min_length=1` 이 2차이지만
    raw INSERT (DB 직접) 로 우회 시 DB CHECK 가 마지막 방어선.
    """

    async def test_empty_content_rejected(self, seed_users, session_factory):
        owner, commenter, _ = await seed_users(3)
        async with session_factory() as s:
            s.add(_mk_post(user_id=owner, post_id="FDP_it_a"))
            await s.commit()

        async with session_factory() as s:
            s.add(FeedPostComment(
                comment_id="FDC_it_a", post_id="FDP_it_a",
                user_id=commenter, content="",
            ))
            with pytest.raises(IntegrityError):
                await s.commit()
