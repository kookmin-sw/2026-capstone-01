"""auth 도메인 단위 테스트 공용 Mock 팩토리."""
from unittest.mock import AsyncMock, MagicMock


class FakeUnitOfWork:
    """`@transactional` 데코레이터의 `async with self.uow as session:` 패턴 충족."""

    def __init__(self, session):
        self._session = session


    async def __aenter__(self):
        return self._session


    async def __aexit__(self, exc_type, exc, tb):
        return False


def make_mock_session() -> MagicMock:
    session = MagicMock(name="session")
    session.flush = AsyncMock()
    return session


# ──────────────────── Repository mocks ────────────────────

def make_user_repo_mock() -> AsyncMock:
    mock = AsyncMock()
    mock.find_by_id.return_value = None
    mock.find_by_id_with_profile.return_value = None
    mock.find_by_ids_with_profile.return_value = {}
    mock.update.return_value = None
    return mock


def make_user_detail_repo_mock() -> AsyncMock:
    mock = AsyncMock()
    mock.find_by_user_id.return_value = None
    mock.update.return_value = None
    mock.save.side_effect = lambda d: d
    return mock


def make_user_travel_style_repo_mock() -> AsyncMock:
    """`UserTravelStyleRepository` — register service 의 `save_all` 만 사용."""
    mock = AsyncMock()
    mock.find_by_user_id.return_value = []
    mock.save_all.side_effect = lambda styles: styles
    return mock


def make_object_storage_mock() -> MagicMock:
    """이미지 업/삭제 관련 — 본 테스트에서는 호출 안 됨 (get_my_profile 만 cover)."""
    storage = MagicMock(name="storage")
    storage.upload_perm = AsyncMock()
    storage.delete = AsyncMock()
    storage.delete_by_prefix = AsyncMock()
    return storage


def make_withdrawal_request_repo_mock() -> AsyncMock:
    """`WithdrawalRequestRepository` (Mongo beanie) 의 모든 public 메서드 mock."""
    mock = AsyncMock()
    mock.upsert.return_value = None
    mock.find_due.return_value = []
    mock.delete_by_user_id.return_value = None
    return mock


def make_inbox_service_mock() -> AsyncMock:
    """인박스 cascade 진입점 mock — withdraw_service 가 탈퇴 cascade 호출 검증용."""
    mock = AsyncMock()
    mock.cascade_user_withdrawn.return_value = 0
    return mock


# ──────────────────── Beanie Document stub ────────────────────

class FakeBeanieFindQuery:
    """`Document.find({...}).delete()` chain 호출 흉내 — `init_beanie` 미호출 환경 우회."""

    def __init__(self):
        self.delete = AsyncMock(return_value=None)


class FakeBeanieDocumentClass:
    """`Document.find(...)` 가 `FakeBeanieFindQuery` 를 반환하도록 흉내내는 stub.

    withdraw `_purge_external` 이 직접 `TripmateImage.find(...).delete()` 형태로 호출하는
    Document 5종 (TripmateImage / TripmatePostDraft / TripmateSearchHistory /
    TourSearchHistory / FriendSearchHistory) 을 일괄 치환.
    """

    def __init__(self, name: str):
        self._name = name
        self.find_call_count = 0
        self.last_filter = None
        # service 가 `await TripmateImage.find({...}).delete()` 형태로 호출하므로 매번 새 query
        self._queries: list[FakeBeanieFindQuery] = []


    def find(self, filter_dict):
        self.find_call_count += 1
        self.last_filter = filter_dict
        q = FakeBeanieFindQuery()
        self._queries.append(q)
        return q


    @property
    def queries(self) -> list[FakeBeanieFindQuery]:
        """테스트가 .delete 호출 검증할 때 사용."""
        return self._queries
