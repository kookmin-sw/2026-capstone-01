"""FeedPostService — 게시물 CRUD e2e 통합 테스트.

S3 / Pillow 는 mock — 외부 인프라 비접근. RDB INSERT/UPDATE/DELETE 와 cascade 흐름 검증.
visibility/caption 정규화, 권한 가드, S3 prefix cleanup 호출까지 cover.

검증 매트릭스:

    | 시나리오                      | 검증                                  |
    |---|---|
    | upload_post 정상              | RDB INSERT + dto 반환 + S3 호출 3회    |
    | get_my_post 본인              | 정상 dto                              |
    | get_my_post 타인 게시물       | PermissionError                        |
    | update_visibility 본인        | RDB UPDATE                             |
    | update_caption 공백만         | NULL 정규화                            |
    | delete_post 본인              | RDB row 삭제 + S3 cleanup 호출        |
    | delete_post 미존재            | FeedNotFoundError                     |
"""
from sqlalchemy import select
import pytest

from app.domain.feed.service.exception import FeedNotFoundError
from app.domain.feed.model.feed_post import FeedPost, FeedVisibility


pytestmark = pytest.mark.integration


# ──────────────────── upload_post ────────────────────

class TestUploadPost:
    """업로드 흐름 — Pillow / S3 mock + 실 RDB INSERT."""

    async def test_creates_post_in_rdb_with_three_urls(
        self, feed_post_service, seed_users, session_factory, feed_storage_mock,
    ):
        [user_id] = await seed_users(1)

        result = await feed_post_service.upload_post(
            user_id=user_id,
            file_bytes=b"image-bytes",
            visibility=FeedVisibility.PUBLIC,
            caption="my first post",
        )

        # S3 3회 (original / small / medium)
        assert feed_storage_mock.upload_to_key.await_count == 3

        # RDB row 검증
        async with session_factory() as session:
            post = await session.get(FeedPost, result.post_id)
            assert post is not None
            assert post.user_id == user_id
            assert post.caption == "my first post"
            assert post.visibility == FeedVisibility.PUBLIC
            assert post.original_url.startswith("https://x/")


    async def test_normalizes_blank_caption_to_null(
        self, feed_post_service, seed_users, session_factory,
    ):
        """공백만 caption → DB 에 NULL (모델 nullable)."""
        [user_id] = await seed_users(1)

        result = await feed_post_service.upload_post(
            user_id=user_id, file_bytes=b"img",
            visibility=FeedVisibility.PUBLIC, caption="   ",
        )

        async with session_factory() as session:
            post = await session.get(FeedPost, result.post_id)
            assert post.caption is None


# ──────────────────── get_my_post ────────────────────

class TestGetMyPost:
    async def test_owner_can_get_own_post(
        self, feed_post_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post()

        result = await feed_post_service.get_my_post(
            user_id=owner_id, post_id=post_id,
        )

        assert result.post_id == post_id


    async def test_other_user_raises_permission_error(
        self, feed_post_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post()
        other_id = await _find_other_user(feed_post_service.uow, owner_id)

        with pytest.raises(PermissionError):
            await feed_post_service.get_my_post(user_id=other_id, post_id=post_id)


    async def test_missing_post_raises_not_found(
        self, feed_post_service, seed_users,
    ):
        [user_id] = await seed_users(1)

        with pytest.raises(FeedNotFoundError):
            await feed_post_service.get_my_post(user_id=user_id, post_id="FDP_ghost")


# ──────────────────── update_visibility / update_caption ────────────────────

class TestUpdateMetadata:
    async def test_update_visibility_persists(
        self, feed_post_service, seed_feed_post, session_factory,
    ):
        post_id, owner_id = await seed_feed_post(visibility=FeedVisibility.PUBLIC)

        await feed_post_service.update_visibility(
            user_id=owner_id, post_id=post_id, visibility=FeedVisibility.PRIVATE,
        )

        async with session_factory() as session:
            post = await session.get(FeedPost, post_id)
            assert post.visibility == FeedVisibility.PRIVATE


    async def test_update_caption_normalizes_blank_to_null(
        self, feed_post_service, seed_feed_post, session_factory,
    ):
        post_id, owner_id = await seed_feed_post()

        await feed_post_service.update_caption(
            user_id=owner_id, post_id=post_id, caption="  ",
        )

        async with session_factory() as session:
            post = await session.get(FeedPost, post_id)
            assert post.caption is None


    async def test_update_other_user_raises_permission_error(
        self, feed_post_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post()
        other_id = await _find_other_user(feed_post_service.uow, owner_id)

        with pytest.raises(PermissionError):
            await feed_post_service.update_visibility(
                user_id=other_id, post_id=post_id, visibility=FeedVisibility.PRIVATE,
            )


# ──────────────────── delete_post ────────────────────

class TestDeletePost:
    async def test_deletes_rdb_and_calls_s3_cleanup(
        self, feed_post_service, seed_feed_post, session_factory, feed_storage_mock,
    ):
        post_id, owner_id = await seed_feed_post()

        await feed_post_service.delete_post(user_id=owner_id, post_id=post_id)

        async with session_factory() as session:
            post = await session.get(FeedPost, post_id)
            assert post is None

        # S3 prefix cleanup 호출
        feed_storage_mock.delete_by_prefix.assert_awaited_once()


    async def test_delete_missing_raises_not_found(
        self, feed_post_service, seed_users,
    ):
        [user_id] = await seed_users(1)

        with pytest.raises(FeedNotFoundError):
            await feed_post_service.delete_post(user_id=user_id, post_id="FDP_ghost")


    async def test_delete_other_user_raises_permission_error(
        self, feed_post_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post()
        other_id = await _find_other_user(feed_post_service.uow, owner_id)

        with pytest.raises(PermissionError):
            await feed_post_service.delete_post(user_id=other_id, post_id=post_id)


# ──────────────────── helpers ────────────────────

async def _find_other_user(uow, exclude_user_id: str) -> str:
    from app.domain.auth.model.user import User, UserStatus

    async with uow as session:
        stmt = select(User.user_id).where(
            User.user_id != exclude_user_id, User.status == UserStatus.ACTIVE,
        ).limit(1)
        result = await session.execute(stmt)
        user_id = result.scalar_one_or_none()
        assert user_id is not None
        return user_id
