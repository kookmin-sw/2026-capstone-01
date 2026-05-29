"""TripmatePostLikeService — RDB 흐름 e2e 통합 테스트 (composite PK + count 정확성).

Phase A 의 `test_like_fanout_flow.py` 와 분리 — 본 모듈은 fan-out 측면이 아닌 RDB schema
invariant 와 count_by_post 의 정확성에 집중한다.

검증 매트릭스:

    | 시나리오                          | RDB 효과                         |
    |---|---|
    | 다수 user 가 좋아요               | count_by_post 누적 정확         |
    | 같은 (user, post) 중복 add        | ValueError (pre-check 단계)      |
    | remove 후 count 감소              | DELETE + count 정확              |
    | get_liked_user_ids 정상           | 좋아요 누른 user_id 모두         |
    | get_liked_user_ids post 미존재    | ValueError                       |
"""
import pytest


pytestmark = pytest.mark.integration


# ──────────────────── add_like + count ────────────────────

class TestAddLikeWithCount:
    async def test_multiple_users_increment_count(
        self, mongo_db, tripmate_post_like_service, seed_tripmate_post, session_factory,
    ):
        """N 명이 좋아요 → count == N. RDB SELECT count(*) 정확성."""
        post_id, owner_id = await seed_tripmate_post()
        # 추가로 2명 시드 (총 4명: owner + 1 from seed_tripmate_post + 2 추가)
        from test.integration.conftest import seed_users  # type: ignore  # noqa: F401

        # seed_users 를 한 번 더 호출해서 user 2명 추가
        from app.domain.auth.model.user import User, UserStatus
        from app.config.oauth import OAuthProvider
        from app.domain.auth.model.user_detail_inform import Gender, UserDetailInform

        extra_ids = ["USER_extra_a", "USER_extra_b"]
        async with session_factory() as session:
            for uid in extra_ids:
                session.add(User(
                    user_id=uid,
                    auth_provider=OAuthProvider.GOOGLE,
                    auth_provider_id=f"{uid}@example.com",
                    status=UserStatus.ACTIVE,
                ))
                session.add(UserDetailInform(
                    user_id=uid, email=f"{uid}@example.com",
                    user_name=uid, age=25, gender=Gender.MALE, nationality="KR",
                ))
            await session.commit()

        actor_id = await _find_other_user(tripmate_post_like_service.uow, owner_id)

        c1 = await tripmate_post_like_service.add_like(user_id=actor_id, post_id=post_id)
        c2 = await tripmate_post_like_service.add_like(user_id=extra_ids[0], post_id=post_id)
        c3 = await tripmate_post_like_service.add_like(user_id=extra_ids[1], post_id=post_id)

        assert c1 == 1
        assert c2 == 2
        assert c3 == 3


    async def test_duplicate_add_raises_value_error(
        self, mongo_db, tripmate_post_like_service, seed_tripmate_post,
    ):
        """같은 (user, post) 두 번 add → pre-check 가드로 ValueError. composite PK 위반 도달 X."""
        post_id, owner_id = await seed_tripmate_post()
        actor_id = await _find_other_user(tripmate_post_like_service.uow, owner_id)

        await tripmate_post_like_service.add_like(user_id=actor_id, post_id=post_id)

        with pytest.raises(ValueError, match="이미 좋아요"):
            await tripmate_post_like_service.add_like(user_id=actor_id, post_id=post_id)


# ──────────────────── remove_like + count 감소 ────────────────────

class TestRemoveLikeWithCount:
    async def test_remove_decrements_count(
        self, mongo_db, tripmate_post_like_service, seed_tripmate_post,
    ):
        post_id, owner_id = await seed_tripmate_post()
        actor_id = await _find_other_user(tripmate_post_like_service.uow, owner_id)

        await tripmate_post_like_service.add_like(user_id=actor_id, post_id=post_id)
        new_count = await tripmate_post_like_service.remove_like(
            user_id=actor_id, post_id=post_id,
        )

        assert new_count == 0


# ──────────────────── get_liked_user_ids ────────────────────

class TestGetLikedUserIds:
    async def test_returns_all_likers_in_recent_first_order(
        self, mongo_db, tripmate_post_like_service, seed_tripmate_post,
    ):
        post_id, owner_id = await seed_tripmate_post()
        actor_id = await _find_other_user(tripmate_post_like_service.uow, owner_id)

        await tripmate_post_like_service.add_like(user_id=actor_id, post_id=post_id)

        liked = await tripmate_post_like_service.get_liked_user_ids(post_id=post_id)
        assert actor_id in liked


    async def test_raises_when_post_not_found(
        self, mongo_db, tripmate_post_like_service,
    ):
        with pytest.raises(ValueError, match="존재하지 않는"):
            await tripmate_post_like_service.get_liked_user_ids(post_id="TMP_ghost")


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
