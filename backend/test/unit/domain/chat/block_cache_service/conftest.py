"""BlockCacheService 단위 테스트 fixtures.

`get_redis_client` 는 모듈 함수 — async function 으로 monkeypatch (실 Redis 비접근).
ChatRoomRepository 는 `@transactional` 안에서 인스턴스화 → 클래스 자체 monkeypatch.
"""
from unittest.mock import AsyncMock
from test.unit.domain.chat.block_cache_service.model_factory import ChatRoomFactory
from test.unit.domain.chat.block_cache_service.mock_factory import (
    FakeUnitOfWork,
    make_chat_room_repo_mock,
    make_mock_session,
    make_redis_mock,
)
import pytest

from app.domain.chat.service.block_cache import BlockCacheService


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture
def chat_room_repo_mock():
    return make_chat_room_repo_mock()


@pytest.fixture
def redis_mock():
    return make_redis_mock()


@pytest.fixture
def service(monkeypatch, mock_session, chat_room_repo_mock, redis_mock):
    monkeypatch.setattr(
        "app.domain.chat.service.block_cache.ChatRoomRepository",
        lambda session: chat_room_repo_mock,
    )
    # `get_redis_client` 는 async function — monkeypatch 도 async 로
    monkeypatch.setattr(
        "app.domain.chat.service.block_cache.get_redis_client",
        AsyncMock(return_value=redis_mock),
    )
    return BlockCacheService(uow=FakeUnitOfWork(mock_session))


@pytest.fixture(autouse=True)
def reset_factories():
    ChatRoomFactory.reset_counter()
    yield
    ChatRoomFactory.reset_counter()
