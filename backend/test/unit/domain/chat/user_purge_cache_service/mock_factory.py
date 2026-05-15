"""UserPurgeCacheService 단위 테스트용 Mock 팩토리.

의존성 둘:
    - `SessionService` (chat 도메인 내부): `revoke_all_sessions` 만 호출
    - `get_redis_client` (모듈 함수): `cleanup_user_data` 의 `DEL unread:{uid}` 만 사용
"""
from unittest.mock import AsyncMock, MagicMock


def make_session_service_mock() -> MagicMock:
    """SessionService — user_purge_cache 는 `revoke_all_sessions` 만 위임 호출."""
    mock = MagicMock(name="session_service")
    mock.revoke_all_sessions = AsyncMock(return_value=0)
    return mock


def make_redis_mock() -> MagicMock:
    """async Redis 클라이언트 — `delete` 만 사용."""
    redis = MagicMock(name="redis")
    redis.delete = AsyncMock(return_value=1)
    return redis
