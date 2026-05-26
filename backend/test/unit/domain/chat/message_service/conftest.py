from test.unit.domain.chat.message_service.mock_factory import (
    FakeUnitOfWork,
    make_chat_member_repo_mock,
    make_chat_room_repo_mock,
    make_dedupe_redis_mock,
    make_fanout_mock,
    make_fcm_mock,
    make_lua_mock,
    make_message_repo_mock,
    make_mock_session,
    make_redis_mock,
)
import pytest

from app.domain.chat.service.message import MessageService


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture
def chat_room_repo_mock():
    return make_chat_room_repo_mock()


@pytest.fixture
def chat_member_repo_mock():
    return make_chat_member_repo_mock()


@pytest.fixture
def message_repo_mock():
    return make_message_repo_mock()


@pytest.fixture
def fanout_mock():
    return make_fanout_mock()


@pytest.fixture
def fcm_mock():
    return make_fcm_mock()


@pytest.fixture
def redis_mock():
    return make_redis_mock()


@pytest.fixture
def redis_dedupe_mock():
    """기본: 새 요청 (SET NX 성공)."""
    return make_dedupe_redis_mock(first_time=True)


@pytest.fixture
def lua_mock():
    return make_lua_mock()


@pytest.fixture
def service(
    monkeypatch,
    mock_session,
    chat_room_repo_mock,
    chat_member_repo_mock,
    message_repo_mock,
    fanout_mock,
    fcm_mock,
    redis_mock,
    redis_dedupe_mock,
    lua_mock,
):
    """Mock 레포 + Mock Redis(hot/dedupe) + Mock Lua 가 주입된 MessageService."""
    monkeypatch.setattr(
        "app.domain.chat.service.message.ChatRoomRepository",
        lambda session: chat_room_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.chat.service.message.ChatRoomMemberRepository",
        lambda session: chat_member_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.chat.service.message.ChatMessageRepository",
        lambda db: message_repo_mock,
    )
    # mongodb.database 참조 회피 — Repository 가 mock 이라 db 인자는 무시됨
    monkeypatch.setattr(
        "app.domain.chat.service.message.mongodb",
        type("FakeMongo", (), {"database": None})(),
    )

    async def _hot():
        return redis_mock
    async def _dedupe():
        return redis_dedupe_mock

    monkeypatch.setattr("app.domain.chat.service.message.get_redis_client", _hot)
    monkeypatch.setattr("app.domain.chat.service.message.get_redis_dedupe_client", _dedupe)

    # lua_scripts 전체 교체
    monkeypatch.setattr("app.domain.chat.service.message.lua_scripts", lua_mock)

    uow = FakeUnitOfWork(mock_session)
    return MessageService(uow=uow, fanout_service=fanout_mock, fcm_service=fcm_mock)
