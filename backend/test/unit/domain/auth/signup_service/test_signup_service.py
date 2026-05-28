"""SignupService — OAuth 콜백 후 회원가입 상태 분기 단위 테스트.

`check_and_register` 의 4가지 outcome:
    - NEW                 — provider 매칭 user 없음 → 신규 생성
    - WITHDRAWAL_PENDING  — user.status == INACTIVE (detail 검사 skip)
    - IN_PROGRESS         — user 있고 ACTIVE 인데 detail 없음
    - COMPLETE            — user 있고 ACTIVE 이고 detail 있음
"""
from test.unit.domain.auth.signup_service.model_factory import (
    UserDetailInformFactory,
    UserFactory,
)
import pytest

from app.domain.auth.model.user import UserStatus
from app.domain.auth.dto.signup import SignupStatus


@pytest.mark.unit
class TestCheckAndRegister:
    """Tests for SignupService.check_and_register."""

    async def test_creates_new_user_when_provider_not_found(
        self, service, user_repo_mock, detail_repo_mock,
    ):
        """provider 매칭 user 없음 → save 후 NEW 반환. detail 검사 skip."""
        user_repo_mock.find_by_provider.return_value = None

        result = await service.check_and_register(
            auth_provider="google", auth_provider_id="new@example.com",
        )

        assert result.status == SignupStatus.NEW
        assert result.user_id == "USER_new_001"  # save side_effect 부여
        user_repo_mock.save.assert_awaited_once()
        detail_repo_mock.find_by_user_id.assert_not_awaited()


    async def test_returns_pending_when_user_inactive(
        self, service, user_repo_mock, detail_repo_mock,
    ):
        """탈퇴 유예(30일) 중 user → detail 무관하게 WITHDRAWAL_PENDING."""
        user = UserFactory.create(user_id="USER_a", status=UserStatus.INACTIVE)
        user_repo_mock.find_by_provider.return_value = user

        result = await service.check_and_register(
            auth_provider="google", auth_provider_id="a@example.com",
        )

        assert result.status == SignupStatus.WITHDRAWAL_PENDING
        assert result.user_id == "USER_a"
        # detail 검사 자체 skip — 탈퇴 유예 상태는 ID 만으로 분기
        detail_repo_mock.find_by_user_id.assert_not_awaited()
        user_repo_mock.save.assert_not_awaited()


    async def test_returns_in_progress_when_detail_missing(
        self, service, user_repo_mock, detail_repo_mock,
    ):
        """user 있지만 detail 미합성 (1차 가입만) → 2차 가입 필요 (IN_PROGRESS)."""
        user = UserFactory.create(user_id="USER_a", status=UserStatus.ACTIVE)
        user_repo_mock.find_by_provider.return_value = user
        detail_repo_mock.find_by_user_id.return_value = None

        result = await service.check_and_register(
            auth_provider="google", auth_provider_id="a@example.com",
        )

        assert result.status == SignupStatus.IN_PROGRESS
        assert result.user_id == "USER_a"
        user_repo_mock.save.assert_not_awaited()


    async def test_returns_complete_when_detail_exists(
        self, service, user_repo_mock, detail_repo_mock,
    ):
        """user + detail 모두 있음 → 정상 가입 완료 (COMPLETE)."""
        user = UserFactory.create(user_id="USER_a", status=UserStatus.ACTIVE)
        user_repo_mock.find_by_provider.return_value = user
        detail_repo_mock.find_by_user_id.return_value = UserDetailInformFactory.create(
            user_id="USER_a",
        )

        result = await service.check_and_register(
            auth_provider="google", auth_provider_id="a@example.com",
        )

        assert result.status == SignupStatus.COMPLETE
        assert result.user_id == "USER_a"
        user_repo_mock.save.assert_not_awaited()


    async def test_existing_active_user_does_not_save(
        self, service, user_repo_mock,
    ):
        """기존 active user — save 호출 없음 (idempotent)."""
        user = UserFactory.create(status=UserStatus.ACTIVE)
        user_repo_mock.find_by_provider.return_value = user

        await service.check_and_register(
            auth_provider="google", auth_provider_id=user.auth_provider_id,
        )

        user_repo_mock.save.assert_not_awaited()
