"""SignupService — OAuth 콜백 후 회원가입 4-way 분기 e2e 통합 테스트.

`check_and_register` 의 outcome 분기를 실 RDB INSERT/SELECT 로 검증.

검증 매트릭스:

    | 입력 상태                         | 기대 outcome           | RDB 효과       |
    |---|---|---|
    | provider 매칭 user 없음           | NEW                    | User 신규 INSERT |
    | user.status == INACTIVE           | WITHDRAWAL_PENDING     | 변경 없음        |
    | user 있고 detail 없음             | IN_PROGRESS            | 변경 없음        |
    | user 있고 detail 있음             | COMPLETE               | 변경 없음        |

unit 테스트가 mock 으로 검증 못 하는 영역:
    - User.user_id 의 `default=generate_user_id` 가 INSERT 시점 자동 부여
    - INACTIVE 분기 시 detail SELECT 자체 skip (RDB round-trip 절약)
"""
from sqlalchemy import select
import pytest

from app.domain.auth.model.user_detail_inform import Gender, UserDetailInform
from app.domain.auth.model.user import User, UserStatus
from app.domain.auth.dto.signup import SignupStatus
from app.config.oauth import OAuthProvider


pytestmark = pytest.mark.integration


# ──────────────────── NEW — 신규 가입 ────────────────────

class TestNewSignup:
    """provider 매칭 user 없음 → 1 차 가입 (User row 생성). detail 검사 skip."""

    async def test_creates_new_user_and_returns_new(
        self, signup_service, session_factory,
    ):
        result = await signup_service.check_and_register(
            auth_provider=OAuthProvider.GOOGLE.value,
            auth_provider_id="brand_new@example.com",
        )

        assert result.status == SignupStatus.NEW
        # 실 RDB 에 INSERT 됨 — user_id default callable 자동 부여
        assert result.user_id is not None
        async with session_factory() as session:
            user = await session.get(User, result.user_id)
            assert user is not None
            assert user.auth_provider_id == "brand_new@example.com"
            assert user.status == UserStatus.ACTIVE


# ──────────────────── WITHDRAWAL_PENDING — INACTIVE 우회 ────────────────────

class TestWithdrawalPending:
    """user.status==INACTIVE 면 detail 검사 skip 후 즉시 PENDING 반환.

    탈뙤 유예(30일) 중인 user 가 OAuth 재로그인 시 → FE 가 cancel 화면으로 라우팅.
    """

    async def test_returns_pending_when_user_inactive(
        self, signup_service, session_factory, seed_users,
    ):
        # seed 한 user 의 status 를 INACTIVE 로 전환
        [user_id] = await seed_users(1)
        async with session_factory() as session:
            user = await session.get(User, user_id)
            provider_id = user.auth_provider_id
            user.status = UserStatus.INACTIVE
            await session.commit()

        result = await signup_service.check_and_register(
            auth_provider=OAuthProvider.GOOGLE.value,
            auth_provider_id=provider_id,
        )

        assert result.status == SignupStatus.WITHDRAWAL_PENDING
        assert result.user_id == user_id


# ──────────────────── IN_PROGRESS — detail 미합성 ────────────────────

class TestInProgress:
    """ACTIVE user 인데 detail 미합성 → 2 차 가입 필요. seed_users 가 detail 까지 만들므로
    inline 으로 detail 없는 user 만 합성."""

    async def test_returns_in_progress_when_detail_missing(
        self, signup_service, session_factory,
    ):
        # detail 없는 user 만 직접 합성
        async with session_factory() as session:
            user = User(
                auth_provider=OAuthProvider.GOOGLE,
                auth_provider_id="no_detail@example.com",
                status=UserStatus.ACTIVE,
            )
            session.add(user)
            await session.commit()
            user_id = user.user_id

        result = await signup_service.check_and_register(
            auth_provider=OAuthProvider.GOOGLE.value,
            auth_provider_id="no_detail@example.com",
        )

        assert result.status == SignupStatus.IN_PROGRESS
        assert result.user_id == user_id


# ──────────────────── COMPLETE — 정상 가입 완료 ────────────────────

class TestComplete:
    """ACTIVE user + detail 모두 합성 → 정상 가입 완료."""

    async def test_returns_complete_when_detail_exists(
        self, signup_service, session_factory, seed_users,
    ):
        # seed_users 가 user + detail 둘 다 합성
        [user_id] = await seed_users(1)
        async with session_factory() as session:
            user = await session.get(User, user_id)
            provider_id = user.auth_provider_id

        result = await signup_service.check_and_register(
            auth_provider=OAuthProvider.GOOGLE.value,
            auth_provider_id=provider_id,
        )

        assert result.status == SignupStatus.COMPLETE
        assert result.user_id == user_id
