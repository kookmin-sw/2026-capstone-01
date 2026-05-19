"""WithdrawService 단위 테스트 fixtures.

WithdrawService 의 의존성:
    - UoW + UserRepository (RDB)         — monkeypatch + mock
    - WithdrawalRequestRepository (Mongo) — `__init__` 안 인스턴스화 → monkeypatch
    - get_object_storage()                — 모듈 함수 → monkeypatch
    - InboxService                        — DI 주입 (cascade_user_withdrawn)
    - Beanie Document 5종 (purge 전용)    — `Document.find().delete()` chain stub
    - invalidate_registered_cache         — 모듈 함수 → monkeypatch (Redis 비접근)

`@transactional` 메서드들 (`request_withdraw`, `_purge_rdb`, `_set_active`) 은 FakeUnitOfWork
+ mock_session 으로 트랜잭션 인터페이스만 충족. 실제 DB 비접근.
"""
from unittest.mock import AsyncMock, MagicMock
from test.unit.domain.auth.withdraw_service.model_factory import UserFactory
from test.unit.domain.auth.mock_factory import (
    FakeBeanieDocumentClass,
    FakeUnitOfWork,
    make_mock_session,
    make_inbox_service_mock,
    make_object_storage_mock,
    make_user_repo_mock,
    make_withdrawal_request_repo_mock,
)
import pytest

from app.domain.auth.service.withdraw import WithdrawService


@pytest.fixture
def mock_session():
    return make_mock_session()


@pytest.fixture
def user_repo_mock():
    return make_user_repo_mock()


@pytest.fixture
def withdrawal_request_repo_mock():
    return make_withdrawal_request_repo_mock()


@pytest.fixture
def storage_mock():
    return make_object_storage_mock()


@pytest.fixture
def inbox_service_mock():
    return make_inbox_service_mock()


@pytest.fixture
def beanie_stubs():
    """purge 가 직접 호출하는 Document 5종 stub. 테스트가 호출 검증 시 참조."""
    return {
        "TripmateImage": FakeBeanieDocumentClass("TripmateImage"),
        "TripmatePostDraft": FakeBeanieDocumentClass("TripmatePostDraft"),
        "TripmateSearchHistory": FakeBeanieDocumentClass("TripmateSearchHistory"),
        "TourSearchHistory": FakeBeanieDocumentClass("TourSearchHistory"),
        "FriendSearchHistory": FakeBeanieDocumentClass("FriendSearchHistory"),
    }


@pytest.fixture
def invalidate_cache_mock():
    """Redis 캐시 무효화 모듈 함수 mock — 실 Redis 비접근."""
    return AsyncMock(return_value=None)


@pytest.fixture
def user_purge_cache_service_mock():
    """chat 도메인 UserPurgeCacheService mock — withdraw 의 cross-domain 훅.

    실제 클래스 import 없이 duck typing — block_cache_service 와 동일 패턴.
    """
    mock = MagicMock(name="user_purge_cache_service")
    mock.revoke_all_sessions = AsyncMock(return_value=None)
    mock.cleanup_user_data = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def service(
    monkeypatch, mock_session,
    user_repo_mock,
    withdrawal_request_repo_mock,
    storage_mock,
    inbox_service_mock,
    beanie_stubs,
    invalidate_cache_mock,
    user_purge_cache_service_mock,
):
    """모든 외부 의존성을 mock 으로 치환한 WithdrawService.

    - `UserRepository`: 트랜잭션 안에서 인스턴스화 → 클래스 자체 monkeypatch
    - `WithdrawalRequestRepository`: `__init__` 에서 `WithdrawalRequestRepository()` 호출 →
      monkeypatch 우선 적용 후 service 인스턴스화
    - `get_object_storage`: 모듈 함수 → mock 반환 lambda
    - Beanie Document 5종: 모듈 import 경로에서 stub 으로 치환
    - `invalidate_registered_cache`: 모듈 함수 → AsyncMock
    """
    monkeypatch.setattr(
        "app.domain.auth.service.withdraw.UserRepository",
        lambda session: user_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.auth.service.withdraw.WithdrawalRequestRepository",
        lambda: withdrawal_request_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.auth.service.withdraw.get_object_storage",
        lambda: storage_mock,
    )
    monkeypatch.setattr(
        "app.domain.auth.service.withdraw.invalidate_registered_cache",
        invalidate_cache_mock,
    )
    for doc_name, stub in beanie_stubs.items():
        monkeypatch.setattr(
            f"app.domain.auth.service.withdraw.{doc_name}",
            stub,
        )

    return WithdrawService(
        uow=FakeUnitOfWork(mock_session),
        inbox_service=inbox_service_mock,
        user_purge_cache_service=user_purge_cache_service_mock,
    )


@pytest.fixture(autouse=True)
def reset_factories():
    UserFactory.reset_counter()
    yield
    UserFactory.reset_counter()
