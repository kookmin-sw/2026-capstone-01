"""피드 좋아요 fan-out e2e 통합 테스트.

`add_like` 호출 → RDB 좋아요 INSERT (트랜잭션) → 트랜잭션 커밋 후 Mongo 인박스 적재 흐름을
실 RDB + 실 Mongo 로 검증.

unit 으로 검증 못 하는 영역:
    - RDB 트랜잭션과 Mongo fan-out 의 분산 정합성 (트랜잭션 분리 패턴 e2e)
    - `uq_inbox_dedup` partial unique 가 실 mongo 에서 중복 항목 방지
    - 본인→본인 caller 가드가 실 RDB INSERT 는 진행하되 Mongo 비접근

검증 매트릭스:

    | 시나리오                        | RDB 좋아요 | Mongo 인박스 |
    |---|---|---|
    | 외부 actor 좋아요               | ✓          | ✓ 적재    |
    | 본인→본인 좋아요                | ✓          | ✗ skip    |
    | 좋아요-취소-좋아요 반복         | RDB 한 번만 | 1건 유지  |
    | remove_like                     | RDB 삭제   | 항목 보존 |
"""
import pytest

from app.domain.notification.model.inbox import (
    InboxItem,
    InboxItemType,
    TargetType,
)


pytestmark = pytest.mark.integration


# ──────────────────── 정상 fan-out ────────────────────

class TestAddLikeFanout:
    """`add_like` 가 RDB INSERT 후 Mongo 에 인박스 항목 적재."""

    async def test_external_actor_creates_inbox_item_in_mongo(
        self, mongo_db, feed_post_like_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post()
        # owner 가 아닌 다른 user 가 시드됐으니 두 번째를 actor 로 사용
        from sqlalchemy import select
        from app.domain.auth.model.user import User
        # seed_feed_post 가 2 명 시드 (owner + 다른 1명) — actor 는 다른 사람
        # owner_id 가 첫 번째라 두 번째 user 가 actor

        actor_id = await _find_other_user(feed_post_like_service.uow, owner_id)

        await feed_post_like_service.add_like(user_id=actor_id, post_id=post_id)

        coll = InboxItem.get_motor_collection()
        doc = await coll.find_one({"recipient_id": owner_id})
        assert doc is not None
        assert doc["actor_id"] == actor_id
        assert doc["type"] == InboxItemType.FEED_LIKE.value
        assert doc["target_type"] == TargetType.FEED_POST.value
        assert doc["target_id"] == post_id


    async def test_self_like_does_not_create_inbox_item(
        self, mongo_db, feed_post_like_service, seed_feed_post,
    ):
        """본인 글 본인 좋아요 — RDB INSERT 는 진행, Mongo 비접근."""
        post_id, owner_id = await seed_feed_post()

        like_count = await feed_post_like_service.add_like(
            user_id=owner_id, post_id=post_id,
        )

        assert like_count == 1  # RDB 좋아요는 들어감
        # Mongo 에는 항목 없음
        coll = InboxItem.get_motor_collection()
        assert await coll.count_documents({}) == 0


# ──────────────────── 멱등성 (partial unique 실 동작) ────────────────────

class TestLikeIdempotency:
    """좋아요-취소-좋아요 race 시 인박스 무한 폭증 방지 — partial unique 실 동작."""

    async def test_like_cancel_like_keeps_single_inbox_item(
        self, mongo_db, feed_post_like_service, seed_feed_post,
    ):
        """X 안 누른 상태에서 좋아요 취소→재좋아요 → 항목 1건만 유지.

        RDB: like row 가 사라졌다가 다시 생김 (count_by_post 흐름 재시작).
        Mongo: 첫 항목이 partial 인덱스에 등록 → 재 INSERT 시 DuplicateKeyError → service
               의 `_safe_insert` 가 swallow → 항목 결국 1건만 존재.
        """
        post_id, owner_id = await seed_feed_post()
        actor_id = await _find_other_user(feed_post_like_service.uow, owner_id)

        await feed_post_like_service.add_like(user_id=actor_id, post_id=post_id)
        await feed_post_like_service.remove_like(user_id=actor_id, post_id=post_id)
        await feed_post_like_service.add_like(user_id=actor_id, post_id=post_id)

        coll = InboxItem.get_motor_collection()
        assert await coll.count_documents({"recipient_id": owner_id}) == 1


# ──────────────────── remove_like — 인박스 보존 정책 ────────────────────

class TestRemoveLikePreservesInboxItem:
    """좋아요 취소 정책 (Q1): 인박스 변경 없음 — 이벤트 사실의 기록."""

    async def test_remove_does_not_delete_inbox_item(
        self, mongo_db, feed_post_like_service, seed_feed_post,
    ):
        post_id, owner_id = await seed_feed_post()
        actor_id = await _find_other_user(feed_post_like_service.uow, owner_id)

        await feed_post_like_service.add_like(user_id=actor_id, post_id=post_id)
        await feed_post_like_service.remove_like(user_id=actor_id, post_id=post_id)

        # 인박스 항목 그대로 — 이벤트 발생 사실의 기록
        coll = InboxItem.get_motor_collection()
        assert await coll.count_documents({"recipient_id": owner_id}) == 1


# ──────────────────── helpers ────────────────────

async def _find_other_user(uow, exclude_user_id: str) -> str:
    """seed_users 가 만든 두 번째 user 찾기 — `exclude_user_id` 외 첫 번째 active user."""
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
