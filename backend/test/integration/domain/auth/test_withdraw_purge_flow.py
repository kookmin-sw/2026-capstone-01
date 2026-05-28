"""WithdrawService.purge e2e 통합 테스트 (RDB + Mongo + 인박스 cascade).

소프트 탈뙤 → 영구 삭제 흐름의 분산 정합성 검증. unit 테스트가 mock 으로 검증할 수 없는
영역:
    - `_purge_rdb` 의 SELECT FOR UPDATE + status 분기 + hard_delete 실 트랜잭션
    - `_purge_external` 단계별 best-effort 가 실 mongo 컬렉션에 반영
    - 인박스 cascade — `recipient_id == user_id` OR `actor_id == user_id` 매칭 모두 삭제
    - STALE_DOC outcome (cancel 후 worker 진입) — RDB 보존 + doc 만 청소

검증 매트릭스:

    | 시나리오                | RDB user | Mongo user data | 인박스 cascade |
    |---|---|---|---|
    | 정상 purge (INACTIVE)   | hard delete | drop          | recipient/actor 삭제 |
    | 미존재 user (NO_USER)   | -           | drop          | cascade 호출 (idempotent) |
    | STALE_DOC (ACTIVE)      | 보존        | doc 만 청소   | cascade 호출 안 함 |
"""
from sqlalchemy import select
import pytest

from app.domain.notification.model.inbox import (
    InboxItem,
    InboxItemType,
    TargetType,
)
from app.domain.auth.model.withdrawal_request import WithdrawalRequest
from app.domain.auth.model.user import User, UserStatus


pytestmark = pytest.mark.integration


# ──────────────────── 정상 purge — INACTIVE → DELETED ────────────────────

class TestPurgeDeletedOutcome:
    """status=INACTIVE 인 user 의 영구 삭제 — RDB hard delete + Mongo 정리 + 인박스 cascade."""

    async def test_hard_deletes_user_from_rdb(
        self, withdraw_service, session_factory, seed_users,
    ):
        user_id, *_ = await seed_users(1)
        await _set_inactive(session_factory, user_id)

        await withdraw_service.purge(user_id=user_id)

        async with session_factory() as session:
            result = await session.execute(
                select(User).where(User.user_id == user_id)
            )
            assert result.scalar_one_or_none() is None


    async def test_cascade_deletes_recipient_and_actor_inbox_items(
        self, withdraw_service, session_factory, seed_users, mongo_db,
    ):
        """탈뙤 user 가 받은(recipient) 항목 + 보낸(actor) 항목 모두 삭제. 무관한 항목 보존."""
        target_user, other_user = await seed_users(2)
        await _set_inactive(session_factory, target_user)

        # target 이 받은 항목
        await InboxItem(
            recipient_id=target_user, actor_id=other_user,
            type=InboxItemType.FEED_LIKE,
            target_type=TargetType.FEED_POST,
            target_id="FDP_1", actor_name="x",
        ).insert()
        # target 이 보낸 항목
        await InboxItem(
            recipient_id=other_user, actor_id=target_user,
            type=InboxItemType.FEED_LIKE,
            target_type=TargetType.FEED_POST,
            target_id="FDP_2", actor_name="x",
        ).insert()
        # 무관한 항목 (보존되어야)
        await InboxItem(
            recipient_id=other_user, actor_id="USER_unrelated",
            type=InboxItemType.FEED_LIKE,
            target_type=TargetType.FEED_POST,
            target_id="FDP_3", actor_name="x",
        ).insert()

        await withdraw_service.purge(user_id=target_user)

        coll = InboxItem.get_motor_collection()
        # target 관련 2건 삭제, 무관한 1건 보존
        assert await coll.count_documents({}) == 1
        remaining = await coll.find_one({})
        assert remaining["actor_id"] == "USER_unrelated"


    async def test_cleans_withdrawal_request_doc(
        self, withdraw_service, session_factory, seed_users,
    ):
        user_id, *_ = await seed_users(1)
        await _set_inactive(session_factory, user_id)

        # withdrawal_request doc 시드
        from datetime import datetime, timezone, timedelta
        await WithdrawalRequest(
            user_id=user_id,
            requested_at=datetime.now(timezone.utc),
            scheduled_purge_at=datetime.now(timezone.utc) - timedelta(days=1),
        ).insert()

        await withdraw_service.purge(user_id=user_id)

        # doc 도 청소됨
        coll = WithdrawalRequest.get_motor_collection()
        assert await coll.count_documents({"user_id": user_id}) == 0


# ──────────────────── STALE_DOC outcome — cancel 복구 ────────────────────

class TestPurgeStaleDocOutcome:
    """status != INACTIVE (cancel 복구 또는 dual-write 잔존) → 외부 리소스 보존, doc 만 청소.

    race-free 안전장치의 핵심: cancel 이 먼저 commit 되어 status=ACTIVE 인 user 의 외부
    데이터를 잘못 날리지 않음.
    """

    async def test_active_user_external_data_preserved(
        self, withdraw_service, session_factory, seed_users, mongo_db,
        storage_mock,
    ):
        """status=ACTIVE → RDB hard delete / Storage cleanup / 인박스 cascade 모두 skip."""
        user_id, other_user = await seed_users(2)
        # status 는 ACTIVE 그대로 (cancel 한 직후 가정)

        # 인박스 1건 시드 (cascade 안 되어야)
        await InboxItem(
            recipient_id=user_id, actor_id=other_user,
            type=InboxItemType.FEED_LIKE,
            target_type=TargetType.FEED_POST,
            target_id="FDP_1", actor_name="x",
        ).insert()

        # withdrawal_request doc 시드
        from datetime import datetime, timezone, timedelta
        await WithdrawalRequest(
            user_id=user_id,
            requested_at=datetime.now(timezone.utc),
            scheduled_purge_at=datetime.now(timezone.utc) - timedelta(days=1),
        ).insert()

        await withdraw_service.purge(user_id=user_id)

        # RDB user 보존
        async with session_factory() as session:
            result = await session.execute(
                select(User).where(User.user_id == user_id)
            )
            user = result.scalar_one_or_none()
            assert user is not None
            assert user.status == UserStatus.ACTIVE

        # 인박스 보존 (cascade 안 함)
        inbox_coll = InboxItem.get_motor_collection()
        assert await inbox_coll.count_documents({"recipient_id": user_id}) == 1

        # Storage cleanup 호출 안 됨
        storage_mock.delete_by_prefix.assert_not_awaited()

        # withdrawal_request doc 만 청소
        wr_coll = WithdrawalRequest.get_motor_collection()
        assert await wr_coll.count_documents({"user_id": user_id}) == 0


# ──────────────────── NO_USER outcome — idempotent 재시도 ────────────────────

class TestPurgeNoUserOutcome:
    """RDB 에 user 없음 (이전 사이클 외부 정리 잔존) → 외부 정리만 idempotent 진행."""

    async def test_runs_external_cleanup_idempotently(
        self, withdraw_service, mongo_db, storage_mock, redis_cache_mock,
    ):
        # RDB 에 user 없는 상태 — 외부 정리만 진행
        await withdraw_service.purge(user_id="USER_ghost")

        # 인박스 cascade 호출 (idempotent — 0건 삭제)
        inbox_coll = InboxItem.get_motor_collection()
        assert await inbox_coll.count_documents({}) == 0

        # 외부 cleanup 도 호출됨
        storage_mock.delete_by_prefix.assert_awaited_once_with("USER_ghost")
        redis_cache_mock.assert_awaited_once_with("USER_ghost")


# ──────────────────── helpers ────────────────────

async def _set_inactive(session_factory, user_id: str) -> None:
    """seed_users 가 만든 ACTIVE user 를 INACTIVE 로 전환."""
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one()
        user.status = UserStatus.INACTIVE
        await session.commit()
