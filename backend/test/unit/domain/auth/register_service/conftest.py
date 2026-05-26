"""RegisterService 단위 테스트 fixtures.

2차 가입 (UserDetailInform + UserTravelStyle 합성) 흐름 검증. service 가 직접
`UserDetailInform(...)` / `UserTravelStyle(...)` 인스턴스화하는데, SQLAlchemy 모델은 단순
attribute 할당 패턴이라 `_sa_instance_state` 가 자동 부여되어 unit 테스트에서도 동작.
별도 stub 불필요 (mute_service test 와 동일 패턴).
"""
from test.unit.domain.auth.register_service.model_factory import (
    UserDetailInformFactory,
    UserFactory,
)
from test.unit.domain.auth.mock_factory import (
    FakeUnitOfWork,
    make_mock_session,
    make_user_detail_repo_mock,
    make_user_repo_mock,
    make_user_travel_style_repo_mock,
)
import pytest

from app.domain.auth.service.register import RegisterService


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture
def user_repo_mock():
    return make_user_repo_mock()


@pytest.fixture
def detail_repo_mock():
    return make_user_detail_repo_mock()


@pytest.fixture
def style_repo_mock():
    return make_user_travel_style_repo_mock()


@pytest.fixture
def service(monkeypatch, mock_session, user_repo_mock, detail_repo_mock, style_repo_mock):
    monkeypatch.setattr(
        "app.domain.auth.service.register.UserRepository",
        lambda session: user_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.auth.service.register.UserDetailInformRepository",
        lambda session: detail_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.auth.service.register.UserTravelStyleRepository",
        lambda session: style_repo_mock,
    )
    return RegisterService(uow=FakeUnitOfWork(mock_session))


@pytest.fixture(autouse=True)
def reset_factories():
    UserFactory.reset_counter()
    UserDetailInformFactory.reset_counter()
    yield
    UserFactory.reset_counter()
    UserDetailInformFactory.reset_counter()
