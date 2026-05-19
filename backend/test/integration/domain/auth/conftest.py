"""auth 도메인 통합 테스트 공통 fixture.

`WithdrawService.purge` 가 RDB hard_delete + Mongo 정리 + 인박스 cascade + Object Storage
cleanup + Redis 캐시 무효화를 단계별로 수행한다. 통합 테스트는:
    - 실 PostgreSQL — `_purge_rdb` 의 SELECT FOR UPDATE + status 분기 + hard delete
    - 실 Mongo — `withdrawal_request` doc + 인박스 cascade
    - Storage / Redis — mock (외부 인프라)

`MONGODB_TEST_URL` 미설정 시 skip — 인박스 cascade 가 Mongo 의존이라 통합 테스트의 핵심.
"""
from unittest.mock import AsyncMock, MagicMock
import pytest_asyncio
import pytest
import os
from motor.motor_asyncio import AsyncIOMotorClient

from app.domain.tripmate.model.tripmate_search_history import TripmateSearchHistory
from app.domain.tripmate.model.tripmate_post_draft import TripmatePostDraft
from app.domain.tripmate.model.tripmate_image import TripmateImage
from app.domain.tour.model.tour_search_history import TourSearchHistory
from app.domain.notification.service.inbox import InboxService
from app.domain.notification.model.inbox import InboxItem
from app.domain.friend.model.search_history import FriendSearchHistory
from app.domain.auth.service.withdraw import WithdrawService
from app.domain.auth.service.signup import SignupService
from app.domain.auth.service.register import RegisterService
from app.domain.auth.service.profile import ProfileService
from app.domain.auth.model.withdrawal_request import WithdrawalRequest


def _require_mongo_url() -> str:
    url = os.getenv("MONGODB_TEST_URL")
    if not url:
        pytest.skip(
            "MONGODB_TEST_URL 환경변수가 설정되지 않아 withdraw 통합 테스트를 건너뜁니다.",
            allow_module_level=False,
        )
    return url


@pytest_asyncio.fixture
async def mongo_db():
    """`_purge_external` 이 건드리는 모든 컬렉션 + 인박스 컬렉션 초기화.

    init_beanie 에 6 개 Document 등록 — withdraw 의 cascade 매트릭스를 모두 cover.
    """
    from beanie import init_beanie

    url = _require_mongo_url()
    client = AsyncIOMotorClient(url, tz_aware=True)
    db = client.get_default_database()

    # withdraw 가 정리 대상으로 호출하는 컬렉션 + 인박스 컬렉션 모두 drop
    for col in [
        "inbox",
        "withdrawal_request",
        "tripmate_image",
        "tripmate_post_draft",
        "tripmate_search_history",
        "tour_search_history",
        "friend_search_history",
    ]:
        await db[col].drop()

    await init_beanie(
        database=db,
        document_models=[
            InboxItem,
            WithdrawalRequest,
            TripmateImage,
            TripmatePostDraft,
            TripmateSearchHistory,
            TourSearchHistory,
            FriendSearchHistory,
        ],
    )

    try:
        yield db
    finally:
        for col in [
            "inbox",
            "withdrawal_request",
            "tripmate_image",
            "tripmate_post_draft",
            "tripmate_search_history",
            "tour_search_history",
            "friend_search_history",
        ]:
            await db[col].drop()
        client.close()


@pytest.fixture
def storage_mock(monkeypatch) -> MagicMock:
    """Object Storage mock — `delete_by_prefix` 만 사용. 실 S3 비접근."""
    storage = MagicMock(name="storage")
    storage.delete_by_prefix = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.domain.auth.service.withdraw.get_object_storage",
        lambda: storage,
    )
    return storage


@pytest.fixture
def redis_cache_mock(monkeypatch) -> AsyncMock:
    """Redis 캐시 무효화 mock — `invalidate_registered_cache` 모듈 함수 직접 치환."""
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.domain.auth.service.withdraw.invalidate_registered_cache",
        mock,
    )
    return mock


@pytest.fixture
def inbox_service(mongo_db) -> InboxService:
    return InboxService()


@pytest.fixture
def chat_purge_service_mock() -> AsyncMock:
    """`UserPurgeCacheService` mock — chat 도메인 cleanup 훅.

    `WithdrawService` 가 두 시점에 호출:
      - request_withdraw commit 후: `revoke_all_sessions(user_id)`
      - purge worker: `cleanup_user_data(user_id)`

    실제 chat Redis / WS 세션 정리는 chat 도메인 단의 검증 영역이라 본 fixture 는
    호출 여부 추적만 가능한 AsyncMock 으로 충분.
    """
    mock = AsyncMock()
    mock.revoke_all_sessions = AsyncMock(return_value=None)
    mock.cleanup_user_data = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def withdraw_service(
    uow, inbox_service, storage_mock, redis_cache_mock, chat_purge_service_mock,
) -> WithdrawService:
    return WithdrawService(
        uow=uow,
        inbox_service=inbox_service,
        user_purge_cache_service=chat_purge_service_mock,
    )


# ──────────────────── RDB 전용 service (mongo 의존 X) ────────────────────

@pytest.fixture
def signup_service(uow) -> SignupService:
    """OAuth 콜백 흐름 — RDB 만 터치. mongo 의존 없으므로 MONGODB_TEST_URL 미설정 환경에서도 동작."""
    return SignupService(uow=uow)


@pytest.fixture
def register_service(uow) -> RegisterService:
    """2차 가입 — RDB 만 터치 (UserDetailInform + UserTravelStyle)."""
    return RegisterService(uow=uow)


@pytest.fixture
def profile_service(uow) -> ProfileService:
    """프로필 조회/수정 + 마이페이지 stats — RDB 만 사용. ObjectStorage 는 stats 경로에서
    호출되지 않으므로 real `get_object_storage` 가 import 단에서 평가돼도 무방.
    """
    return ProfileService(uow=uow)
