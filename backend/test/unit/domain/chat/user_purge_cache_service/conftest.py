"""UserPurgeCacheService 단위 테스트 fixtures.

`get_redis_client` 는 모듈 함수 — async function 으로 monkeypatch (실 Redis 비접근).
`SessionService` 는 생성자 주입 → mock 객체 그대로 전달.
"""
from unittest.mock import AsyncMock

import pytest

from app.domain.chat.service.user_purge_cache import UserPurgeCacheService

from test.unit.domain.chat.user_purge_cache_service.mock_factory import (
    make_redis_mock,
    make_session_service_mock,
)


@pytest.fixture
def session_service_mock():
    return make_session_service_mock()


@pytest.fixture
def redis_mock():
    return make_redis_mock()


@pytest.fixture
def service(monkeypatch, session_service_mock, redis_mock):
    # `get_redis_client` 는 async function — monkeypatch 도 async 로
    monkeypatch.setattr(
        "app.domain.chat.service.user_purge_cache.get_redis_client",
        AsyncMock(return_value=redis_mock),
    )
    return UserPurgeCacheService(session_service=session_service_mock)
