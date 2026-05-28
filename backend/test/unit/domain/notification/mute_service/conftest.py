from test.unit.domain.notification.mock_factory import (
    ChatRoomMemberRepositoryMockFactory,
    FakeUnitOfWork,
    UserRepositoryMockFactory,
    make_mock_session,
)
import pytest

from app.domain.notification.service.mute import MuteService


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture
def user_repo_mock():
    return UserRepositoryMockFactory.create()


@pytest.fixture
def chat_member_repo_mock():
    return ChatRoomMemberRepositoryMockFactory.create()


@pytest.fixture
def service(monkeypatch, mock_session, user_repo_mock, chat_member_repo_mock):
    monkeypatch.setattr(
        "app.domain.notification.service.mute.UserRepository",
        lambda session: user_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.notification.service.mute.ChatRoomMemberRepository",
        lambda session: chat_member_repo_mock,
    )

    uow = FakeUnitOfWork(mock_session)
    return MuteService(uow=uow)
