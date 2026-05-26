"""TripmatePostService — 게시물 CRUD e2e 통합 테스트.

S3 / Mongo image repo mock — RDB 흐름만 통합. visibility 검증 없음 (tripmate 도메인은
모두 PUBLIC 노출). 권한/이미지 cleanup/cascade 흐름이 핵심.

검증 매트릭스:

    | 시나리오                       | 검증                              |
    |---|---|
    | create_post 정상               | RDB INSERT + author dto           |
    | get_post 미존재                | ValueError                        |
    | update_post 권한 없음          | PermissionError                   |
    | update_post 정상               | RDB persist                       |
    | delete_post 권한 없음          | PermissionError                   |
    | delete_post 정상               | RDB row 삭제 (CASCADE 좋아요/이미지) |
    | toggle_display 정상            | is_displayed 토글                 |
"""
from sqlalchemy import select
import pytest
from datetime import date

from app.domain.tripmate.model.tripmate_post import (
    CompanionType, PreferredGender, TripmatePost,
)


pytestmark = pytest.mark.integration


# ──────────────────── create_post ────────────────────

class TestCreatePost:
    async def test_creates_in_rdb_and_returns_dto(
        self, tripmate_post_service, seed_users, session_factory,
    ):
        [user_id] = await seed_users(1)

        result = await tripmate_post_service.create_post(
            user_id=user_id,
            title="제주 여행",
            content="제주도 6/1 ~ 6/5",
            preferred_age_min=20,
            preferred_age_max=30,
            preferred_gender=PreferredGender.ANY,
            region="제주",
            travel_start_date=date(2026, 6, 1),
            travel_end_date=date(2026, 6, 5),
            companion_type=CompanionType.FRIEND,
            image_urls=None,
        )

        assert result.title == "제주 여행"
        async with session_factory() as session:
            post = await session.get(TripmatePost, result.post_id)
            assert post is not None
            assert post.user_id == user_id


# ──────────────────── get_post ────────────────────

class TestGetPost:
    async def test_returns_dto_when_post_exists(
        self, tripmate_post_service, seed_tripmate_post,
    ):
        post_id, _ = await seed_tripmate_post()

        result = await tripmate_post_service.get_post(post_id=post_id)

        assert result.post_id == post_id


    async def test_raises_when_post_not_found(self, tripmate_post_service):
        with pytest.raises(ValueError, match="존재하지 않는"):
            await tripmate_post_service.get_post(post_id="TMP_ghost")


# ──────────────────── update_post ────────────────────

class TestUpdatePost:
    async def test_other_user_raises_permission_error(
        self, tripmate_post_service, seed_tripmate_post,
    ):
        post_id, owner_id = await seed_tripmate_post()
        other_id = await _find_other_user(tripmate_post_service.uow, owner_id)

        with pytest.raises(PermissionError):
            await tripmate_post_service.update_post(
                post_id=post_id, user_id=other_id,
                title="hacked", content="content",
                preferred_age_min=20, preferred_age_max=30,
                preferred_gender=PreferredGender.ANY,
                region="hacked",
                travel_start_date=date(2026, 6, 1),
                travel_end_date=date(2026, 6, 5),
                companion_type=CompanionType.FRIEND,
            )


    async def test_owner_can_update_persists(
        self, tripmate_post_service, seed_tripmate_post, session_factory,
    ):
        post_id, owner_id = await seed_tripmate_post()

        await tripmate_post_service.update_post(
            post_id=post_id, user_id=owner_id,
            title="수정된 제목",
            content="수정된 내용 입니다 부산 7월",  # ck_content_min_length(>=10) 통과
            preferred_age_min=25, preferred_age_max=35,
            preferred_gender=PreferredGender.MALE,
            region="부산",
            travel_start_date=date(2026, 7, 1),
            travel_end_date=date(2026, 7, 5),
            companion_type=CompanionType.SOLE,
        )

        async with session_factory() as session:
            post = await session.get(TripmatePost, post_id)
            assert post.title == "수정된 제목"
            assert post.region == "부산"


# ──────────────────── delete_post ────────────────────

class TestDeletePost:
    async def test_other_user_raises_permission_error(
        self, tripmate_post_service, seed_tripmate_post,
    ):
        post_id, owner_id = await seed_tripmate_post()
        other_id = await _find_other_user(tripmate_post_service.uow, owner_id)

        with pytest.raises(PermissionError):
            await tripmate_post_service.delete_post(post_id=post_id, user_id=other_id)


    async def test_owner_can_delete_post_row_removed(
        self, tripmate_post_service, seed_tripmate_post, session_factory,
    ):
        post_id, owner_id = await seed_tripmate_post()

        await tripmate_post_service.delete_post(post_id=post_id, user_id=owner_id)

        async with session_factory() as session:
            post = await session.get(TripmatePost, post_id)
            assert post is None


    async def test_missing_raises_value_error(
        self, tripmate_post_service, seed_users,
    ):
        [user_id] = await seed_users(1)

        with pytest.raises(ValueError, match="존재하지 않는"):
            await tripmate_post_service.delete_post(
                post_id="TMP_ghost", user_id=user_id,
            )


# ──────────────────── toggle_display ────────────────────

class TestToggleDisplay:
    async def test_toggles_is_displayed(
        self, tripmate_post_service, seed_tripmate_post, session_factory,
    ):
        post_id, owner_id = await seed_tripmate_post()
        # 시드 default: is_displayed=True

        result = await tripmate_post_service.toggle_display(
            post_id=post_id, user_id=owner_id,
        )

        assert result is False
        async with session_factory() as session:
            post = await session.get(TripmatePost, post_id)
            assert post.is_displayed is False


    async def test_other_user_raises_permission_error(
        self, tripmate_post_service, seed_tripmate_post,
    ):
        post_id, owner_id = await seed_tripmate_post()
        other_id = await _find_other_user(tripmate_post_service.uow, owner_id)

        with pytest.raises(PermissionError):
            await tripmate_post_service.toggle_display(
                post_id=post_id, user_id=other_id,
            )


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
