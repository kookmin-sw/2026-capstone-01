"""tour 도메인 통합 테스트 공통 fixture.

PlaceService / FavoritePlaceService 는 Mongo (`place` 컬렉션) + RDB (`favorite_place`) 합성.
실 mongo 의 `2dsphere` geo 인덱스 + RDB 즐겨찾기 cross-table 동작이 핵심 검증 영역.

기존 `test_tour_plan_flow.py` 는 PlaceRepository 를 mock 으로 우회 — RDB only. 본 conftest
는 실 Mongo 가 추가로 필요하므로 MONGODB_TEST_URL 환경변수 미설정 시 mongo_db fixture 만 skip.
"""
import pytest_asyncio
import pytest
import os
from motor.motor_asyncio import AsyncIOMotorClient

from app.domain.tour.service.place import PlaceService
from app.domain.tour.service.favorite_place import FavoritePlaceService
from app.domain.tour.model.place import Place


def _require_mongo_url() -> str:
    url = os.getenv("MONGODB_TEST_URL")
    if not url:
        pytest.skip(
            "MONGODB_TEST_URL 환경변수가 설정되지 않아 tour Mongo 통합 테스트를 건너뜁니다.",
            allow_module_level=False,
        )
    return url


@pytest_asyncio.fixture
async def mongo_db():
    """`place` 컬렉션 초기화 + beanie init.

    `2dsphere` geo 인덱스가 init_beanie 시점에 자동 생성 (idempotent) — geo 쿼리 검증 가능.
    """
    from beanie import init_beanie

    url = _require_mongo_url()
    client = AsyncIOMotorClient(url, tz_aware=True)
    db = client.get_default_database()

    await db.place.drop()
    await init_beanie(database=db, document_models=[Place])

    try:
        yield db
    finally:
        await db.place.drop()
        client.close()


@pytest.fixture
def place_service(mongo_db, uow) -> PlaceService:
    return PlaceService(uow=uow)


@pytest.fixture
def favorite_place_service(mongo_db, uow) -> FavoritePlaceService:
    return FavoritePlaceService(uow=uow)


@pytest_asyncio.fixture
async def seed_place(mongo_db):
    """Mongo `place` 컬렉션에 테스트 장소 1건 시드.

    GeoJSON Point 좌표 (lng, lat) — `2dsphere` 인덱스 호환.
    """
    from app.domain.tour.model.place import Place, PlaceLocation

    async def _seed(
        *,
        place_id: str = "PLACE_IT_001",
        display_name: str = "Test Place",
        category: str = "restaurant",
        address: str = "Seoul",
        lat: float = 37.5,
        lng: float = 127.0,
    ) -> str:
        place = Place(
            place_id=place_id,
            display_name=display_name,
            category=category,
            address=address,
            location=PlaceLocation(coordinates=[lng, lat]),
        )
        await place.insert()
        return place_id

    return _seed
