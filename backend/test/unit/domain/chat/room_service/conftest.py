from test.unit.domain.chat.room_service.model_factory import (
    ChatRoomFactory,
    UserBlockFactory,
    UserFactory,
)
from test.unit.domain.chat.room_service.mock_factory import (
    FakeUnitOfWork,
    make_chat_member_repo_mock,
    make_chat_message_repo_mock,
    make_chat_room_repo_mock,
    make_fanout_mock,
    make_friendship_repo_mock,
    make_mock_session,
    make_redis_mock,
    make_user_block_repo_mock,
    make_user_repo_mock,
)
import pytest

from app.domain.chat.service.room import RoomService


@pytest.fixture(autouse=True)
def reset_factories():
    UserFactory.reset_counter()
    ChatRoomFactory.reset_counter()
    UserBlockFactory.reset_counter()
    yield
    UserFactory.reset_counter()
    ChatRoomFactory.reset_counter()
    UserBlockFactory.reset_counter()


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
def user_block_repo_mock():
    return make_user_block_repo_mock()


@pytest.fixture
def user_repo_mock():
    return make_user_repo_mock()


@pytest.fixture
def friendship_repo_mock():
    return make_friendship_repo_mock()


@pytest.fixture
def message_repo_mock():
    return make_chat_message_repo_mock()


@pytest.fixture
def fanout_mock():
    return make_fanout_mock()


@pytest.fixture
def message_service_mock():
    """RoomService 가 Phase 2 #2 에서 system 메시지 발행용으로 의존하는 stub."""
    from unittest.mock import AsyncMock, MagicMock
    mock = MagicMock(name="message_service")
    mock.send_system_message = AsyncMock()
    return mock


@pytest.fixture
def redis_mock():
    return make_redis_mock()


@pytest.fixture
def service(
    monkeypatch,
    mock_session,
    chat_room_repo_mock,
    chat_member_repo_mock,
    user_block_repo_mock,
    user_repo_mock,
    friendship_repo_mock,
    message_repo_mock,
    fanout_mock,
    redis_mock,
    message_service_mock,
):
    """Mock 레포 + Mock Redis / Fanout 이 주입된 RoomService."""
    monkeypatch.setattr(
        "app.domain.chat.service.room.ChatRoomRepository",
        lambda session: chat_room_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.chat.service.room.ChatRoomMemberRepository",
        lambda session: chat_member_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.chat.service.room.UserBlockRepository",
        lambda session: user_block_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.chat.service.room.UserRepository",
        lambda session: user_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.chat.service.room.FriendshipRepository",
        lambda session: friendship_repo_mock,
    )
    # invite 시 ChatMessageRepository(mongodb.database) 를 만들지만 mongo 연결은 불필요.
    monkeypatch.setattr(
        "app.domain.chat.service.room.ChatMessageRepository",
        lambda db: message_repo_mock,
    )

    async def _get_client():
        return redis_mock
    monkeypatch.setattr(
        "app.domain.chat.service.room.get_redis_client",
        _get_client,
    )

    uow = FakeUnitOfWork(mock_session)
    return RoomService(
        uow=uow, fanout_service=fanout_mock, message_service=message_service_mock,
    )
