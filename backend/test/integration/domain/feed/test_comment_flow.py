"""FeedPostCommentService — visibility / 권한 / content 정규화 e2e 통합 테스트.

`test_comment_fanout_flow.py` 와 분리 — 본 모듈은 fan-out 측면이 아닌:
    - visibility 가드 (PUBLIC/FRIENDS/PRIVATE)
    - content 빈/공백 정규화 (DB CHECK constraint 까지의 다단계 방어선)
    - delete 작성자 본인만 가드
    - 댓글 페이지네이션 (최신순)

검증 매트릭스:

    | 시나리오                           | 기대                              |
    |---|---|
    | PRIVATE post 타인 댓글             | FeedNotFoundError                 |
    | FRIENDS post 비친구 댓글           | FeedNotFoundError                 |
    | 차단 관계 댓글                     | FeedBlockedError                  |
    | 빈 content                         | ValueError (strip 후 빈)          |
    | 공백만 content                     | ValueError                        |
    | 다른 작성자 delete                 | PermissionError                   |
    | post mismatch                      | FeedPostCommentNotFoundError      |
    | list_comments 최신순               | created_at DESC                   |
"""
import pytest

from app.domain.feed.service.exception import (
    FeedBlockedError,
    FeedNotFoundError,
    FeedPostCommentNotFoundError,
)
from app.domain.feed.model.feed_post import FeedVisibility


pytestmark = pytest.mark.integration


# ──────────────────── visibility / 차단 가드 ────────────────────

class TestVisibilityGuards:
    async def test_friends_post_non_friend_cannot_comment(
        self, mongo_db, feed_post_comment_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post(visibility=FeedVisibility.FRIENDS)
        actor_id = await _find_other_user(feed_post_comment_service.uow, owner_id)

        with pytest.raises(FeedNotFoundError):
            await feed_post_comment_service.create_comment(
                user_id=actor_id, post_id=post_id, content="hi",
            )


    async def test_private_post_stranger_cannot_comment(
        self, mongo_db, feed_post_comment_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post(visibility=FeedVisibility.PRIVATE)
        actor_id = await _find_other_user(feed_post_comment_service.uow, owner_id)

        with pytest.raises(FeedNotFoundError):
            await feed_post_comment_service.create_comment(
                user_id=actor_id, post_id=post_id, content="hi",
            )


    async def test_blocked_user_raises_blocked_error(
        self, mongo_db, feed_post_comment_service, seed_feed_post, seed_block,
    ):
        post_id, owner_id = await seed_feed_post(visibility=FeedVisibility.PUBLIC)
        actor_id = await _find_other_user(feed_post_comment_service.uow, owner_id)

        await seed_block(blocker=owner_id, blocked=actor_id)

        with pytest.raises(FeedBlockedError):
            await feed_post_comment_service.create_comment(
                user_id=actor_id, post_id=post_id, content="hi",
            )


# ──────────────────── content 정규화 — 다단계 방어선 ────────────────────

class TestContentNormalization:
    """schema(min_length=1) → service(strip 후 빈 거절) → DB CHECK 의 다단계 방어선."""

    async def test_whitespace_only_raises_value_error(
        self, mongo_db, feed_post_comment_service, seed_feed_post,
    ):
        """공백만 입력 → schema 의 min_length 통과하지만 service 의 strip 가드가 잡음."""
        post_id, owner_id = await seed_feed_post()

        with pytest.raises(ValueError, match="비어"):
            await feed_post_comment_service.create_comment(
                user_id=owner_id, post_id=post_id, content="   ",
            )


    async def test_strips_leading_trailing_whitespace(
        self, mongo_db, feed_post_comment_service, seed_feed_post,
    ):
        """양 끝 공백 strip 후 저장. 의미 없는 공백 제거."""
        post_id, owner_id = await seed_feed_post()

        comment = await feed_post_comment_service.create_comment(
            user_id=owner_id, post_id=post_id, content="  hello  ",
        )

        assert comment.content == "hello"


# ──────────────────── delete — 작성자 본인만 ────────────────────

class TestDeleteAuthorOnly:
    async def test_other_author_raises_permission_error(
        self, mongo_db, feed_post_comment_service, seed_feed_post,
    ):
        """게시물 owner 라도 다른 사람의 댓글은 못 지움 (MVP 정책)."""
        post_id, owner_id = await seed_feed_post()
        actor_id = await _find_other_user(feed_post_comment_service.uow, owner_id)

        comment = await feed_post_comment_service.create_comment(
            user_id=actor_id, post_id=post_id, content="hello",
        )

        # owner 가 actor 의 댓글 삭제 시도 → 거절
        with pytest.raises(PermissionError):
            await feed_post_comment_service.delete_comment(
                user_id=owner_id, post_id=post_id, comment_id=comment.comment_id,
            )


    async def test_post_mismatch_raises_not_found(
        self, mongo_db, feed_post_comment_service, seed_feed_post,
    ):
        """다른 post_id 와 함께 comment_id 넘기면 mismatch → NotFound 일원화."""
        post_id, owner_id = await seed_feed_post()

        comment = await feed_post_comment_service.create_comment(
            user_id=owner_id, post_id=post_id, content="hello",
        )

        with pytest.raises(FeedPostCommentNotFoundError):
            await feed_post_comment_service.delete_comment(
                user_id=owner_id, post_id="FDP_other", comment_id=comment.comment_id,
            )


    async def test_author_can_delete_own_comment(
        self, mongo_db, feed_post_comment_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post()

        comment = await feed_post_comment_service.create_comment(
            user_id=owner_id, post_id=post_id, content="my comment",
        )

        # raise 없이 정상 종료
        await feed_post_comment_service.delete_comment(
            user_id=owner_id, post_id=post_id, comment_id=comment.comment_id,
        )


# ──────────────────── list_comments — 최신순 ────────────────────

class TestListComments:
    async def test_lists_in_recent_first_order(
        self, mongo_db, feed_post_comment_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post()

        await feed_post_comment_service.create_comment(
            user_id=owner_id, post_id=post_id, content="first",
        )
        await feed_post_comment_service.create_comment(
            user_id=owner_id, post_id=post_id, content="second",
        )
        await feed_post_comment_service.create_comment(
            user_id=owner_id, post_id=post_id, content="third",
        )

        result = await feed_post_comment_service.list_comments(
            viewer_id=owner_id, post_id=post_id,
        )

        assert len(result.comments) == 3
        # 최신순 — 마지막에 작성한 게 먼저
        assert result.comments[0].content == "third"
        assert result.comments[2].content == "first"


# ──────────────────── helpers ────────────────────

async def _find_other_user(uow, exclude_user_id: str) -> str:
    from sqlalchemy import select
    from app.domain.auth.model.user import User, UserStatus

    async with uow as session:
        stmt = select(User.user_id).where(
            User.user_id != exclude_user_id, User.status == UserStatus.ACTIVE,
        ).limit(1)
        result = await session.execute(stmt)
        user_id = result.scalar_one_or_none()
        assert user_id is not None
        return user_id
