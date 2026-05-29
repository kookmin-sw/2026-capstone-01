"""notification 도메인 단위 테스트 공용 Mock 팩토리."""
from unittest.mock import AsyncMock, MagicMock


class FakeAsyncContextManager:
    async def __aenter__(self):
        return self


    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeUnitOfWork:
    """`@transactional` 의 `async with self.uow as session:` 패턴 충족."""

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

class FcmTokenRepositoryMockFactory:
    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.save.return_value = None
        mock.find_by_token.return_value = None
        mock.find_by_user_id.return_value = []
        mock.find_by_user_ids.return_value = []
        mock.update.return_value = None
        mock.delete.return_value = None
        mock.delete_by_token.return_value = None
        mock.delete_by_tokens.return_value = None
        return mock


class UserRepositoryMockFactory:
    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.find_by_id.return_value = None
        mock.find_unmuted_user_ids.return_value = set()
        mock.update.return_value = None
        return mock


class ChatRoomMemberRepositoryMockFactory:
    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.find.return_value = None
        mock.find_pushable_user_ids_in_room.return_value = set()
        mock.update.return_value = None
        return mock


class InboxRepositoryMockFactory:
    """인박스 (Mongo) Repository Mock — beanie/motor 의존 없이 동작 검증용.

    각 메서드 default 는 "비어 있음" / "no-op" 흐름. 개별 테스트가 케이스별 override.
    """

    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.insert.return_value = None
        mock.find_by_recipient.return_value = []
        mock.count_unread.return_value = 0
        mock.hide.return_value = False  # default: 미존재/타인소유
        mock.mark_all_read.return_value = 0
        mock.delete_by_user.return_value = 0
        return mock


# ──────────────────── FCM batch response helper ────────────────────

def make_fcm_batch_response(
    success_results: list[bool],
    error_results: list | None = None,
) -> MagicMock:
    """`messaging.send_each_for_multicast` 가 돌려주는 BatchResponse 흉내.

    Args:
        success_results: 토큰별 성공 여부 (True/False) — 길이 = 토큰 수
        error_results: 실패 토큰의 exception 객체 리스트 (성공 위치는 None)
    """
    error_results = error_results or [None] * len(success_results)
    responses = []
    for ok, err in zip(success_results, error_results):
        resp = MagicMock()
        resp.success = ok
        resp.exception = err
        responses.append(resp)
    batch = MagicMock()
    batch.responses = responses
    batch.success_count = sum(1 for r in success_results if r)
    return batch
