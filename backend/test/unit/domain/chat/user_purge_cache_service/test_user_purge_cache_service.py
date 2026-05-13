"""UserPurgeCacheService — 회원 탈퇴 시 chat 도메인 Redis 정리 훅 단위 테스트.

검증 대상:
    - `revoke_all_sessions`: SessionService 위임 + 실패 swallow (fail-open, TTL fallback)
    - `cleanup_user_data` : `unread:{uid}` DEL + 실패 swallow (best-effort)

`BlockCacheService` 와 동일한 cross-domain hook 패턴 — auth 도메인에서 호출되는 facade
이므로 본 테스트는 위임/예외 정책 위주.
"""
import pytest

from app.core.chat.redis_key import unread_key


# ──────────────────────────────────────────────────────────────────
# revoke_all_sessions — 탈퇴 요청 commit 후 호출
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRevokeAllSessions:
    """Tests for UserPurgeCacheService.revoke_all_sessions."""

    async def test_delegates_to_session_service(
        self, service, session_service_mock,
    ):
        """단순 위임 — SessionService.revoke_all_sessions 호출 전달."""
        session_service_mock.revoke_all_sessions.return_value = 3

        await service.revoke_all_sessions("USER_a")

        session_service_mock.revoke_all_sessions.assert_awaited_once_with("USER_a")

    async def test_swallows_exception_fail_open(
        self, service, session_service_mock,
    ):
        """SessionService 가 던져도 호출자에 전파 안 됨 — 90s TTL fallback 정책.

        탈퇴 요청 라우터가 cleanup 실패로 419 응답을 막지 않도록 fail-open.
        """
        session_service_mock.revoke_all_sessions.side_effect = RuntimeError("redis down")

        # 예외 없이 정상 반환
        await service.revoke_all_sessions("USER_a")


# ──────────────────────────────────────────────────────────────────
# cleanup_user_data — 영구 삭제 시점 (purge worker) 호출
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestCleanupUserData:
    """Tests for UserPurgeCacheService.cleanup_user_data."""

    async def test_deletes_unread_key(self, service, redis_mock):
        """TTL 없는 unread HASH 명시 정리 — purge 시점에만 호출."""
        await service.cleanup_user_data("USER_a")

        redis_mock.delete.assert_awaited_once_with(unread_key("USER_a"))

    async def test_does_not_call_session_revoke(
        self, service, redis_mock, session_service_mock,
    ):
        """cleanup_user_data 는 데이터성 키만 — 세션은 이미 request_withdraw 단계에서 처리."""
        await service.cleanup_user_data("USER_a")

        session_service_mock.revoke_all_sessions.assert_not_awaited()

    async def test_swallows_exception_best_effort(self, service, redis_mock):
        """Redis 장애 시에도 swallow — 전체 purge 흐름은 영향받지 않음."""
        redis_mock.delete.side_effect = RuntimeError("redis down")

        # 예외 없이 정상 반환 (best-effort)
        await service.cleanup_user_data("USER_a")
