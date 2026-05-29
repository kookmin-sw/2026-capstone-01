"""SignupService 단위 테스트 fixtures.

OAuth 콜백 후 1차 가입 / 상태 분기 (NEW / WITHDRAWAL_PENDING / IN_PROGRESS / COMPLETE)
검증. service 가 직접 `User(...)` 인스턴스화하므로 Stub 으로 치환 — SQLAlchemy 모델의
default=generate_user_id 가 instance 시점이 아닌 INSERT 시점에 부여되기 때문에 stub 이 더
명료. save 시점에 user_id 부여하는 side_effect 로 신규 가입 흐름 시뮬레이션.
"""
from test.unit.domain.auth.signup_service.model_factory import (
    UserDetailInformFactory,
    UserFactory,
)
from test.unit.domain.auth.mock_factory import (
    FakeUnitOfWork,
    make_mock_session,
    make_user_detail_repo_mock,
    make_user_repo_mock,
)
import pytest

from app.domain.auth.service.signup import SignupService


class _UserStub:
    """`User` SQLAlchemy 모델의 lightweight 대체.

    service 가 `User(auth_provider=..., auth_provider_id=...)` 로 인스턴스화한 뒤 save 후
    `user.user_id` 에 접근 → save side_effect 가 user_id 부여하도록 user_repo_mock 에 hook.
    """

    def __init__(self, **kwargs):
        self.user_id = None
        self.status = None
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture
def user_repo_mock():
    mock = make_user_repo_mock()
    mock.find_by_provider = mock.find_by_id  # 동일 AsyncMock 재사용은 안 됨 — 별도

    # find_by_provider 는 별도 AsyncMock 로 명시적 부여
    from unittest.mock import AsyncMock
    mock.find_by_provider = AsyncMock(return_value=None)

    # save side_effect: user_id 가 None 이면 새 ID 부여 → 신규 가입 흐름 시뮬레이션
    def _save_with_id(user):
        if getattr(user, "user_id", None) is None:
            user.user_id = "USER_new_001"
        return user
    mock.save.side_effect = _save_with_id
    return mock


@pytest.fixture
def detail_repo_mock():
    return make_user_detail_repo_mock()


@pytest.fixture
def service(monkeypatch, mock_session, user_repo_mock, detail_repo_mock):
    """UserRepository / UserDetailInformRepository / User 클래스를 stub 으로 치환."""
    monkeypatch.setattr(
        "app.domain.auth.service.signup.UserRepository",
        lambda session: user_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.auth.service.signup.UserDetailInformRepository",
        lambda session: detail_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.auth.service.signup.User",
        _UserStub,
    )
    return SignupService(uow=FakeUnitOfWork(mock_session))


@pytest.fixture(autouse=True)
def reset_factories():
    UserFactory.reset_counter()
    UserDetailInformFactory.reset_counter()
    yield
    UserFactory.reset_counter()
    UserDetailInformFactory.reset_counter()
