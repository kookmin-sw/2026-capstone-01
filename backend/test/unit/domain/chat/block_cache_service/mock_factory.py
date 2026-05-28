"""BlockCacheService 단위 테스트용 Mock 팩토리.

chat 도메인의 service 별 mock_factory 컨벤션 (room_service / fanout_service 등) 일관.
의존성: ChatRoomRepository (RDB 조회), redis client (캐시 DEL).
"""
from unittest.mock import AsyncMock, MagicMock


class FakeUnitOfWork:
    """`@transactional` 의 `async with self.uow as session:` 패턴 충족."""

    def __init__(self, session):
        self._session = session


    async def __aenter__(self):
        return self._session


    async def __aexit__(self, exc_type, exc, tb):
        return False


def make_mock_session() -> MagicMock:
    session = MagicMock(name="session")
    session.flush = AsyncMock()
    return session


def make_chat_room_repo_mock() -> AsyncMock:
    """`ChatRoomRepository` — block_cache 는 `find_direct_by_pair` 만 사용."""
    mock = AsyncMock()
    mock.find_direct_by_pair.return_value = None  # 기본: 1:1 방 없음
    return mock


def make_redis_mock() -> MagicMock:
    """async Redis 클라이언트 — `delete` 만 사용."""
    redis = MagicMock(name="redis")
    redis.delete = AsyncMock(return_value=1)
    return redis
