"""feed 도메인 통합 테스트 공통 fixture.

서비스 → 레포지토리 → 실 PostgreSQL/Mongo 까지 검증한다. 인박스 fan-out 흐름 검증을 위해
실 Mongo 가 필요하며, MONGODB_TEST_URL 환경변수 미설정 시 skip.

`feed_post_like_service` / `feed_post_comment_service` 는 InboxService 의존성을 받기
때문에 fan-out 통합 시 실 mongo 컬렉션에 인박스 항목이 적재되는 흐름까지 e2e 로 검증 가능.
"""
import pytest_asyncio
import pytest
import os
from motor.motor_asyncio import AsyncIOMotorClient

from app.domain.notification.service.inbox import InboxService
from app.domain.notification.model.inbox import InboxItem
from app.domain.feed.service.feed_post_like import FeedPostLikeService
from app.domain.feed.service.feed_post_comment import FeedPostCommentService


def _require_mongo_url() -> str:
    url = os.getenv("MONGODB_TEST_URL")
    if not url:
        pytest.skip(
            "MONGODB_TEST_URL 환경변수가 설정되지 않아 feed fan-out 통합 테스트를 건너뜁니다.",
            allow_module_level=False,
        )
    return url


@pytest_asyncio.fixture
async def mongo_db():
    """`inbox` 컬렉션 초기화 + beanie init.

    매 테스트 fresh — drop + 인덱스 재생성으로 격리. partial unique 인덱스가 fan-out 의
    멱등 흐름을 보장하는지 검증되는 영역.
    """
    from beanie import init_beanie

    url = _require_mongo_url()
    client = AsyncIOMotorClient(url, tz_aware=True)
    db = client.get_default_database()

    await db.inbox.drop()
    await init_beanie(database=db, document_models=[InboxItem])

    try:
        yield db
    finally:
        await db.inbox.drop()
        client.close()


@pytest.fixture
def inbox_service(mongo_db) -> InboxService:
    return InboxService()


@pytest.fixture
def feed_post_like_service(uow, inbox_service) -> FeedPostLikeService:
    return FeedPostLikeService(uow=uow, inbox_service=inbox_service)


# ──────────────────── feed_post_service (S3 + Pillow mock) ────────────────────

@pytest.fixture
def feed_storage_mock(monkeypatch):
    """S3 stub — `upload_to_key` 가 prefix/filename 합성한 URL 반환. delete_by_prefix 추적."""
    from unittest.mock import AsyncMock, MagicMock

    storage = MagicMock(name="feed-storage")

    async def _upload(data, *, prefix, filename, content_type):
        return f"https://x/{prefix}/{filename}"

    storage.upload_to_key = AsyncMock(side_effect=_upload)
    storage.delete_by_prefix = AsyncMock()

    monkeypatch.setattr(
        "app.domain.feed.service.feed_post.get_object_storage",
        lambda: storage,
    )
    return storage


@pytest.fixture
def process_feed_image_mock(monkeypatch):
    """Pillow `process_feed_image` mock — bytes 처리는 통합 가치 작음 (unit 으로 cover)."""
    from types import SimpleNamespace

    def _mock(file_bytes):
        return SimpleNamespace(
            original=SimpleNamespace(data=b"orig", file_ext="jpg", content_type="image/jpeg"),
            small=SimpleNamespace(data=b"small", file_ext="jpg", content_type="image/jpeg"),
            medium=SimpleNamespace(data=b"medium", file_ext="jpg", content_type="image/jpeg"),
        )

    monkeypatch.setattr(
        "app.domain.feed.service.feed_post.process_feed_image",
        _mock,
    )


@pytest.fixture
def feed_post_service(uow, feed_storage_mock, process_feed_image_mock, inbox_service):
    """FeedPostService — `delete_post` 의 인박스 cascade (soft hide) 의존성 포함."""
    from app.domain.feed.service.feed_post import FeedPostService
    return FeedPostService(uow=uow, inbox_service=inbox_service)


@pytest.fixture
def feed_post_comment_service(uow, inbox_service) -> FeedPostCommentService:
    return FeedPostCommentService(uow=uow, inbox_service=inbox_service)


@pytest_asyncio.fixture
async def seed_feed_post(session_factory, seed_users):
    """feed_post 1건 시드 — owner 1명 + 게시물. (post_id, owner_id) 반환.

    visibility 는 PUBLIC default (가시성 통과). 차단/친구 관계 없이 모든 viewer 가 볼 수 있음.
    """
    from app.domain.feed.model.feed_post import FeedPost, FeedVisibility

    async def _seed(visibility: FeedVisibility = FeedVisibility.PUBLIC):
        owner_id, *_ = await seed_users(2)
        async with session_factory() as session:
            post = FeedPost(
                user_id=owner_id,
                visibility=visibility,
                caption=None,
                original_url="https://x/o.jpg",
                thumbnail_small_url="https://x/s.jpg",
                thumbnail_medium_url="https://x/m.jpg",
            )
            session.add(post)
            await session.commit()
            return post.post_id, owner_id

    return _seed


@pytest_asyncio.fixture
async def seed_friendship(session_factory):
    """두 user 사이 ACCEPTED 친구 관계 시드. visibility=FRIENDS 케이스 검증용."""
    from app.domain.friend.model.friendship import Friendship, FriendshipStatus

    async def _seed(user_a: str, user_b: str):
        async with session_factory() as session:
            session.add(Friendship(
                requester_id=user_a,
                addressee_id=user_b,
                status=FriendshipStatus.ACCEPTED,
            ))
            await session.commit()

    return _seed


@pytest_asyncio.fixture
async def seed_block(session_factory):
    """blocker → blocked 차단 관계 시드. FeedBlockedError 검증용."""
    from app.domain.friend.model.user_block import UserBlock

    async def _seed(blocker: str, blocked: str):
        async with session_factory() as session:
            session.add(UserBlock(blocker_id=blocker, blocked_id=blocked))
            await session.commit()

    return _seed
