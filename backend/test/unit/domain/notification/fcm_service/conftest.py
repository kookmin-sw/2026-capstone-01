from unittest.mock import MagicMock
from test.unit.domain.notification.mock_factory import (
    ChatRoomMemberRepositoryMockFactory,
    FakeUnitOfWork,
    FcmTokenRepositoryMockFactory,
    UserRepositoryMockFactory,
    make_mock_session,
)
import pytest

from app.domain.notification.service.fcm import FcmService


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture
def fcm_token_repo_mock():
    return FcmTokenRepositoryMockFactory.create()


@pytest.fixture
def user_repo_mock():
    return UserRepositoryMockFactory.create()


@pytest.fixture
def chat_member_repo_mock():
    return ChatRoomMemberRepositoryMockFactory.create()


@pytest.fixture
def messaging_send_mock():
    """`messaging.send_each_for_multicast` 모킹용. 테스트가 `return_value` / `side_effect` 설정."""
    return MagicMock(name="messaging.send_each_for_multicast")


@pytest.fixture
def service(
    monkeypatch,
    mock_session,
    fcm_token_repo_mock,
    user_repo_mock,
    chat_member_repo_mock,
    messaging_send_mock,
):
    """모든 외부 의존성 mock 처리된 FcmService."""
    monkeypatch.setattr(
        "app.domain.notification.service.fcm.FcmTokenRepository",
        lambda session: fcm_token_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.notification.service.fcm.UserRepository",
        lambda session: user_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.notification.service.fcm.ChatRoomMemberRepository",
        lambda session: chat_member_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.notification.service.fcm.messaging.send_each_for_multicast",
        messaging_send_mock,
    )
    # init_fcm 미호출 환경 — 어떤 객체든 반환만 하면 됨 (실제 호출은 monkeypatched send 가 가로챔)
    monkeypatch.setattr(
        "app.domain.notification.service.fcm.get_fcm_app",
        lambda: MagicMock(name="firebase_app"),
    )

    uow = FakeUnitOfWork(mock_session)
    return FcmService(uow=uow)
