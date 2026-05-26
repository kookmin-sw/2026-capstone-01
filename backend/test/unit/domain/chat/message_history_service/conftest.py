from test.unit.domain.chat.message_history_service.mock_factory import (
    FakeUnitOfWork,
    make_chat_member_repo_mock,
    make_chat_room_repo_mock,
    make_friendship_repo_mock,
    make_message_repo_mock,
    make_mock_session,
    make_redis_mock,
    make_user_repo_mock,
)
import pytest

from app.domain.chat.service.message_history import MessageHistoryService


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
def user_repo_mock():
    return make_user_repo_mock()


@pytest.fixture
def friendship_repo_mock():
    return make_friendship_repo_mock()


@pytest.fixture
def redis_mock():
    return make_redis_mock()


@pytest.fixture
def service(
    monkeypatch,
    mock_session,
    chat_room_repo_mock,
    chat_member_repo_mock,
    message_repo_mock,
    user_repo_mock,
    friendship_repo_mock,
    redis_mock,
):
    """Mock 레포/Redis 가 주입된 MessageHistoryService. mongodb.database 는 우회."""
    monkeypatch.setattr(
        "app.domain.chat.service.message_history.ChatRoomRepository",
        lambda session: chat_room_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.chat.service.message_history.ChatRoomMemberRepository",
        lambda session: chat_member_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.chat.service.message_history.ChatMessageRepository",
        lambda db: message_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.chat.service.message_history.UserRepository",
        lambda session: user_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.chat.service.message_history.FriendshipRepository",
        lambda session: friendship_repo_mock,
    )
    # mongodb singleton 의 database 접근 회피
    monkeypatch.setattr(
        "app.domain.chat.service.message_history.mongodb",
        type("FakeMongo", (), {"database": None})(),
    )

    async def _get_client():
        return redis_mock
    monkeypatch.setattr(
        "app.domain.chat.service.message_history.get_redis_client",
        _get_client,
    )

    uow = FakeUnitOfWork(mock_session)
    return MessageHistoryService(uow=uow)
