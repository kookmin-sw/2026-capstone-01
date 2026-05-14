"""tripmate 도메인 통합 테스트 공통 fixture.

서비스 → 레포지토리 → 실 PostgreSQL/Mongo 까지 검증한다. 인박스 fan-out 흐름 검증을 위해
실 Mongo 가 필요하며, MONGODB_TEST_URL 환경변수 미설정 시 skip.

feed 도메인의 conftest 와 패턴 일관 — 도메인별 격리 유지.
"""
import os
from datetime import date

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from app.domain.notification.model.inbox import InboxItem
from app.domain.notification.service.inbox import InboxService
from app.domain.tripmate.model.tripmate_image import TripmateImage
from app.domain.tripmate.model.tripmate_post_draft import TripmatePostDraft
from app.domain.tripmate.service.tripmate_image import TripmateImageService
from app.domain.tripmate.service.tripmate_post_draft import TripmatePostDraftService
from app.domain.tripmate.service.tripmate_post_like import TripmatePostLikeService


def _require_mongo_url() -> str:
    url = os.getenv("MONGODB_TEST_URL")
    if not url:
        pytest.skip(
            "MONGODB_TEST_URL 환경변수가 설정되지 않아 tripmate fan-out 통합 테스트를 건너뜁니다.",
            allow_module_level=False,
        )
    return url


@pytest_asyncio.fixture
async def mongo_db():
    """tripmate 도메인 통합 테스트용 컬렉션 초기화 + beanie init.

    `inbox` (fan-out 통합), `tripmate_post_draft` / `tripmate_image` (Phase C 의 draft
    / image 테스트). 매 테스트 fresh — drop + init_beanie 재호출로 인덱스 재생성.
    """
    from beanie import init_beanie

    url = _require_mongo_url()
    client = AsyncIOMotorClient(url, tz_aware=True)
    db = client.get_default_database()

    for col in ["inbox", "tripmate_post_draft", "tripmate_image"]:
        await db[col].drop()
    await init_beanie(
        database=db,
        document_models=[InboxItem, TripmatePostDraft, TripmateImage],
    )

    try:
        yield db
    finally:
        for col in ["inbox", "tripmate_post_draft", "tripmate_image"]:
            await db[col].drop()
        client.close()


@pytest.fixture
def inbox_service(mongo_db) -> InboxService:
    return InboxService()


@pytest.fixture
def tripmate_post_like_service(uow, inbox_service) -> TripmatePostLikeService:
    return TripmatePostLikeService(uow=uow, inbox_service=inbox_service)


# ──────────────────── tripmate_post_service (S3 + Mongo image mock) ────────────────────

@pytest.fixture
def tripmate_storage_mock(monkeypatch):
    """S3 stub — post 삭제/수정 시 `delete_many` 만 사용."""
    from unittest.mock import AsyncMock, MagicMock

    storage = MagicMock(name="tripmate-storage")
    storage.delete_many = AsyncMock()
    monkeypatch.setattr(
        "app.domain.tripmate.service.tripmate_post.get_object_storage",
        lambda: storage,
    )
    return storage


@pytest.fixture
def tripmate_image_mongo_repo_mock(monkeypatch):
    """`TripmateImageRepository` (Mongo) mock — service 가 init 시점에 인스턴스화."""
    from unittest.mock import AsyncMock

    mock = AsyncMock()
    mock.delete_by_urls = AsyncMock()
    monkeypatch.setattr(
        "app.domain.tripmate.service.tripmate_post.TripmateImageRepository",
        lambda: mock,
    )
    return mock


@pytest.fixture
def tripmate_post_draft_service(mongo_db) -> TripmatePostDraftService:
    """draft service — Mongo 단독 (RDB 의존 없음). mongo_db init 만 필요."""
    return TripmatePostDraftService()


@pytest.fixture
def tripmate_image_storage_mock(monkeypatch):
    """TripmateImageService 의 Storage stub — upload_perm / delete 만 사용."""
    from unittest.mock import AsyncMock, MagicMock

    storage = MagicMock(name="image-storage")
    storage.upload_perm = AsyncMock(side_effect=_upload_perm_side_effect)
    storage.delete = AsyncMock()
    storage.delete_many = AsyncMock()
    monkeypatch.setattr(
        "app.domain.tripmate.service.tripmate_image.get_object_storage",
        lambda: storage,
    )
    return storage


def _upload_perm_side_effect(file, file_name, content_type, *, prefix):
    """Storage `upload_perm` 동작 흉내 — prefix/filename 합성한 URL 반환."""
    return f"https://x/{prefix}/{file_name}"


@pytest.fixture
def tripmate_image_service(mongo_db, uow, tripmate_image_storage_mock) -> TripmateImageService:
    """TripmateImageService — RDB + 실 Mongo + Storage mock."""
    return TripmateImageService(uow=uow)


@pytest.fixture
def tripmate_post_service(
    uow, tripmate_storage_mock, tripmate_image_mongo_repo_mock, inbox_service,
):
    """TripmatePostService — RDB + S3/Mongo image mock + 인박스 cascade 의존성."""
    from app.domain.tripmate.service.tripmate_post import TripmatePostService
    from app.domain.tripmate.service.tripmate_post_draft import TripmatePostDraftService

    draft_service = TripmatePostDraftService()
    return TripmatePostService(
        uow=uow, draft_service=draft_service, inbox_service=inbox_service,
    )


@pytest_asyncio.fixture
async def seed_tripmate_post(session_factory, seed_users):
    """tripmate_post 1건 시드 — owner + 2명 유저. (post_id, owner_id) 반환."""
    from app.domain.tripmate.model.tripmate_post import (
        CompanionType, PreferredGender, TripmatePost,
    )

    async def _seed():
        owner_id, *_ = await seed_users(2)
        async with session_factory() as session:
            post = TripmatePost(
                user_id=owner_id,
                title="여행 같이 가실 분",
                content="제주 여행 동행 구합니다",
                preferred_age_min=20,
                preferred_age_max=30,
                preferred_gender=PreferredGender.ANY,
                region="제주",
                travel_start_date=date(2026, 6, 1),
                travel_end_date=date(2026, 6, 5),
                companion_type=CompanionType.FRIEND,
            )
            session.add(post)
            await session.commit()
            return post.post_id, owner_id

    return _seed
