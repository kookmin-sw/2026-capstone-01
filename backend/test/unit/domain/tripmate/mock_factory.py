"""tripmate 도메인 단위 테스트 공용 Mock 팩토리.

`@transactional` 의 `async with self.uow as session:` 패턴을 충족하는 FakeUnitOfWork +
TripmatePost / TripmatePostLike / UserDetailInform / InboxService 의 AsyncMock 을
한 곳에서 관리한다. friend / notification 도메인의 `*RepositoryMockFactory` 패턴과 일관.
"""
from unittest.mock import AsyncMock, MagicMock


class FakeUnitOfWork:
    """`@transactional` 데코레이터의 컨텍스트 매니저 인터페이스 충족."""

    def __init__(self, session):
        self._session = session


    async def __aenter__(self):
        return self._session


    async def __aexit__(self, exc_type, exc, tb):
        return False


def make_mock_session() -> MagicMock:
    session = MagicMock(name="session")
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.get = AsyncMock(return_value=None)
    return session


# ──────────────────── Repository mocks ────────────────────

class TripmatePostRepositoryMockFactory:
    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.find_by_id.return_value = None
        mock.find_by_id_with_detail.return_value = None
        mock.find_all_displayed.return_value = []
        mock.search.return_value = []
        mock.save.side_effect = lambda post: post
        mock.update.side_effect = lambda post: post
        mock.delete.return_value = None
        return mock


class TripmatePostLikeRepositoryMockFactory:
    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.find_by_user_and_post.return_value = None  # 기본: 안 누른 상태
        mock.find_user_ids_by_post.return_value = []
        mock.count_by_post.return_value = 0
        mock.save.side_effect = lambda like: like
        mock.delete_by_user_and_post.return_value = None
        return mock


class UserDetailInformRepositoryMockFactory:
    """fan-out actor snapshot 합성 시 사용되는 detail repo mock.

    default 는 None (detail 결손 케이스) — actor_name="" / profile_image_url=None fallback
    동작을 기본으로 노출. 정상 케이스는 개별 테스트가 return_value 를 override.
    """

    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.find_by_user_id.return_value = None
        return mock


# ──────────────────── External service mocks ────────────────────

def make_inbox_service_mock() -> AsyncMock:
    """인박스 fan-out 진입점 mock — 호출 검증용. 본인→본인 skip 가드는 service 가 처리."""
    mock = AsyncMock()
    mock.notify_tripmate_like.return_value = None
    mock.notify_feed_like.return_value = None
    mock.notify_feed_comment.return_value = None
    mock.cascade_user_withdrawn.return_value = 0
    mock.cascade_post_deleted.return_value = 0
    return mock


# ──────────────────── 추가 Repository / 보조 mocks ────────────────────

class TripmatePostImageRepositoryMockFactory:
    @classmethod
    def create(cls) -> AsyncMock:
        mock = AsyncMock()
        mock.find_by_post_id.return_value = []
        mock.save_all.return_value = None
        mock.delete_by_post_id.return_value = None
        return mock


def make_tripmate_image_mongo_repo_mock() -> AsyncMock:
    """`TripmateImageRepository` (Mongo beanie). delete_by_urls 만 사용됨."""
    mock = AsyncMock()
    mock.delete_by_urls.return_value = None
    return mock


def make_object_storage_mock() -> MagicMock:
    """tripmate 도메인이 사용하는 storage 메서드: upload_perm / delete / delete_many."""
    storage = MagicMock(name="storage")
    storage.upload_perm = AsyncMock(return_value="https://img/uploaded.jpg")
    storage.delete = AsyncMock()
    storage.delete_many = AsyncMock()
    return storage


def make_tripmate_image_mongo_repo_full_mock() -> AsyncMock:
    """`TripmateImageRepository` (Mongo beanie) — image_service 가 사용하는 모든 메서드.

    `make_tripmate_image_mongo_repo_mock` 는 delete_by_urls 만 노출하지만 image_service 는
    save / find_by_user_id / find_by_image_id / delete_by_image_id / delete_by_image_ids
    까지 사용하므로 별도 factory.
    """
    mock = AsyncMock()
    mock.save.side_effect = lambda img: img
    mock.find_by_user_id.return_value = []
    mock.find_by_image_id.return_value = None
    mock.delete_by_image_id.return_value = None
    mock.delete_by_image_ids.return_value = None
    mock.delete_by_urls.return_value = None
    mock.delete_by_user_id.return_value = None
    return mock


def make_tripmate_post_image_repo_mock() -> AsyncMock:
    """`TripmatePostImageRepository` (RDB) — image_service cleanup 이 `find_urls_by_user_id` 사용."""
    mock = AsyncMock()
    mock.find_urls_by_user_id.return_value = []
    return mock


def make_draft_service_mock() -> AsyncMock:
    """TripmatePostDraftService — `delete_draft` 만 사용 (best-effort)."""
    mock = AsyncMock()
    mock.delete_draft.return_value = None
    return mock
