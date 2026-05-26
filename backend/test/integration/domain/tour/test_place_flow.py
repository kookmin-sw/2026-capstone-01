"""PlaceService — Mongo 거리순 검색 + RDB 즐겨찾기 합성 e2e 통합 테스트.

핵심 검증: 실 mongo `2dsphere` geo 인덱스 + `$geoNear` aggregation pipeline 이 동작.
unit 으로 검증 못 하는 영역 (raw mongo 쿼리 실행).

검증 매트릭스:

    | 시나리오                           | 검증                                |
    |---|---|
    | get_nearby_places — 가까운 순       | distance 누적 (가까운 → 먼)          |
    | get_nearby_places — 빈 결과         | empty list, next_cursor=None         |
    | get_nearby_places — 즐겨찾기 매핑   | RDB 즐겨찾기 → is_favorite=True     |
    | get_place_by_id — 정상              | dto                                  |
    | get_place_by_id — 미존재            | None                                 |
    | search_nearby_places — 키워드 매칭  | display_name match                   |
"""
import pytest

from app.domain.tour.model.favorite_place import FavoritePlace


pytestmark = pytest.mark.integration


# ──────────────────── get_nearby_places (geo 쿼리) ────────────────────

class TestGetNearbyPlaces:
    """`$geoNear` aggregation 이 실 mongo 의 `2dsphere` 인덱스를 사용하는지 e2e."""

    async def test_returns_places_sorted_by_distance(
        self, place_service, seed_place,
    ):
        """3개 place 시드, lat/lng 기준 거리순 정렬 검증."""
        # 기준점 (37.5, 127.0)
        # P_close: 같은 좌표 → 거리 0
        # P_mid: 0.01 lat 차이 → ~1.1km
        # P_far: 0.1 lat 차이 → ~11km
        await seed_place(place_id="P_close", lat=37.5, lng=127.0)
        await seed_place(place_id="P_mid", lat=37.51, lng=127.0)
        await seed_place(place_id="P_far", lat=37.6, lng=127.0)

        result = await place_service.get_nearby_places(
            lat=37.5, lng=127.0, user_id="",
        )

        # 거리순 정렬
        place_ids = [p.place_id for p in result.places]
        assert place_ids == ["P_close", "P_mid", "P_far"]
        assert result.places[0].distance < result.places[1].distance < result.places[2].distance


    async def test_returns_empty_when_no_places(self, place_service):
        result = await place_service.get_nearby_places(
            lat=37.5, lng=127.0, user_id="",
        )

        assert result.places == []
        assert result.next_cursor is None


    async def test_marks_favorited_places(
        self, place_service, seed_place, seed_users, session_factory,
    ):
        """RDB favorite_place 매칭 시 is_favorite=True 합성."""
        [user_id] = await seed_users(1)
        await seed_place(place_id="P_a", lat=37.5, lng=127.0)
        await seed_place(place_id="P_b", lat=37.51, lng=127.0)

        # P_a 만 즐겨찾기
        async with session_factory() as session:
            session.add(FavoritePlace(user_id=user_id, place_id="P_a"))
            await session.commit()

        result = await place_service.get_nearby_places(
            lat=37.5, lng=127.0, user_id=user_id,
        )

        by_id = {p.place_id: p for p in result.places}
        assert by_id["P_a"].is_favorite is True
        assert by_id["P_b"].is_favorite is None  # 미즐겨찾기는 None (presence 표현)


    async def test_no_favorited_when_user_id_empty(
        self, place_service, seed_place,
    ):
        """비로그인 (user_id="") → favorited 조회 skip, 모두 None."""
        await seed_place(place_id="P_a")

        result = await place_service.get_nearby_places(
            lat=37.5, lng=127.0, user_id="",
        )

        assert result.places[0].is_favorite is None


# ──────────────────── get_place_by_id ────────────────────

class TestGetPlaceById:
    async def test_returns_dto_when_place_exists(self, place_service, seed_place):
        await seed_place(place_id="P_x", display_name="Custom Name")

        result = await place_service.get_place_by_id(place_id="P_x", user_id="")

        assert result is not None
        assert result.place_id == "P_x"
        assert result.display_name == "Custom Name"


    async def test_returns_none_when_not_found(self, place_service):
        result = await place_service.get_place_by_id(
            place_id="P_ghost", user_id="",
        )

        assert result is None


# ──────────────────── search_nearby_places ────────────────────

class TestSearchNearbyPlaces:
    """키워드 + 거리순 합성. display_name / category 매칭."""

    async def test_returns_only_matching_keyword(
        self, place_service, seed_place,
    ):
        await seed_place(place_id="P_pizza", display_name="피자집", lat=37.5, lng=127.0)
        await seed_place(place_id="P_chicken", display_name="치킨집", lat=37.51, lng=127.0)

        result = await place_service.search_nearby_places(
            lat=37.5, lng=127.0, keyword="피자", user_id="",
        )

        place_ids = [p.place_id for p in result.places]
        assert place_ids == ["P_pizza"]
