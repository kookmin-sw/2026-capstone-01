from test.unit.domain.chat.session_service.mock_factory import (
    make_mock_fanout,
    make_mock_redis,
)
import pytest

from app.domain.chat.service.session import SessionService


@pytest.fixture
def fanout_mock():
    return make_mock_fanout()


@pytest.fixture
def redis_mock():
    return make_mock_redis()


@pytest.fixture
def service(monkeypatch, redis_mock, fanout_mock):
    """Mock Redis / Fanout 이 주입된 SessionService."""
    # SessionService 는 메서드마다 `await get_redis_client()` 호출 → 이걸 교체
    async def _get_client():
        return redis_mock

    monkeypatch.setattr(
        "app.domain.chat.service.session.get_redis_client",
        _get_client,
    )
    return SessionService(fanout_service=fanout_mock)
