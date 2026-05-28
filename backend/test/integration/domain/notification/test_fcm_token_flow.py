"""FcmService 토큰 등록/해제 통합 — 분기 + UNIQUE/CASCADE 까지 실 DB 검증.

핵심:
    - 신규 INSERT
    - 동일 (user, token) 재등록 → no-op
    - 동일 token 다른 user → owner 만 교체 (디바이스 계정 전환)
    - 해제 idempotent (없거나 타인 소유는 조용히 종료)
    - user CASCADE 로 토큰 자동 정리 (회원 탈퇴 영구 삭제 시)
"""
from test.integration.domain.notification.conftest import fetch_tokens_by_user
from sqlalchemy import delete
import pytest

from app.domain.notification.model.fcm_token import FcmToken
from app.domain.auth.model.user import User


pytestmark = pytest.mark.integration


# ──────────────────── register_token ────────────────────

class TestRegisterTokenFlow:
    async def test_new_token_is_inserted(
        self, fcm_service, session_factory, seed_users,
    ):
        [user_id] = await seed_users(1)

        result = await fcm_service.register_token(user_id=user_id, token="tok-A")

        rows = await fetch_tokens_by_user(session_factory, user_id)
        assert len(rows) == 1
        assert rows[0].token == "tok-A"
        assert result.fcm_token_id == rows[0].fcm_token_id


    async def test_same_user_same_token_is_noop(
        self, fcm_service, session_factory, seed_users,
    ):
        [user_id] = await seed_users(1)

        first = await fcm_service.register_token(user_id=user_id, token="tok-A")
        second = await fcm_service.register_token(user_id=user_id, token="tok-A")

        rows = await fetch_tokens_by_user(session_factory, user_id)
        assert len(rows) == 1  # 중복 row 생성 안 됨
        assert first.fcm_token_id == second.fcm_token_id  # 같은 row 그대로


    async def test_different_user_same_token_swaps_owner(
        self, fcm_service, session_factory, seed_users,
    ):
        """디바이스 계정 전환 케이스 — 같은 토큰이 다른 user 로 재등록되면 owner 만 교체."""
        [user_a, user_b] = await seed_users(2)

        await fcm_service.register_token(user_id=user_a, token="tok-shared")
        await fcm_service.register_token(user_id=user_b, token="tok-shared")

        a_rows = await fetch_tokens_by_user(session_factory, user_a)
        b_rows = await fetch_tokens_by_user(session_factory, user_b)
        assert a_rows == []  # 이전 owner 잃음
        assert len(b_rows) == 1
        assert b_rows[0].token == "tok-shared"


    async def test_one_user_can_register_multiple_tokens(
        self, fcm_service, session_factory, seed_users,
    ):
        """한 유저가 여러 디바이스 보유 가능 — UNIQUE 는 token 컬럼만."""
        [user_id] = await seed_users(1)

        await fcm_service.register_token(user_id=user_id, token="tok-1")
        await fcm_service.register_token(user_id=user_id, token="tok-2")

        rows = await fetch_tokens_by_user(session_factory, user_id)
        assert len(rows) == 2
        assert {r.token for r in rows} == {"tok-1", "tok-2"}


# ──────────────────── unregister_token ────────────────────

class TestUnregisterTokenFlow:
    async def test_owner_can_delete(
        self, fcm_service, session_factory, seed_users,
    ):
        [user_id] = await seed_users(1)
        await fcm_service.register_token(user_id=user_id, token="tok-A")

        await fcm_service.unregister_token(user_id=user_id, token="tok-A")

        rows = await fetch_tokens_by_user(session_factory, user_id)
        assert rows == []


    async def test_non_owner_silent_noop(
        self, fcm_service, session_factory, seed_users,
    ):
        """타인 토큰 해제 시도는 정보 누출 차단을 위해 조용히 종료 — 실 row 는 보존."""
        [user_a, user_b] = await seed_users(2)
        await fcm_service.register_token(user_id=user_a, token="tok-A")

        # B 가 A 의 토큰 해제 시도
        await fcm_service.unregister_token(user_id=user_b, token="tok-A")

        rows = await fetch_tokens_by_user(session_factory, user_a)
        assert len(rows) == 1  # 보존


    async def test_nonexistent_token_silent_noop(
        self, fcm_service, seed_users,
    ):
        [user_id] = await seed_users(1)
        # 등록한 적 없는 토큰 — 예외 없이 종료
        await fcm_service.unregister_token(user_id=user_id, token="never-existed")


# ──────────────────── CASCADE on user delete ────────────────────

class TestFcmTokenCascade:
    async def test_user_delete_cascades_tokens(
        self, fcm_service, session_factory, seed_users,
    ):
        """`fcm_token.user_id` FK 가 `ondelete=CASCADE` — user 삭제 시 토큰 자동 제거.

        회원 탈퇴 영구 삭제 흐름이 별도 토큰 정리 로직 없이 작동하는 근거.
        """
        [user_id] = await seed_users(1)
        await fcm_service.register_token(user_id=user_id, token="tok-1")
        await fcm_service.register_token(user_id=user_id, token="tok-2")

        async with session_factory() as session:
            await session.execute(delete(User).where(User.user_id == user_id))
            await session.commit()

        rows = await fetch_tokens_by_user(session_factory, user_id)
        assert rows == []
