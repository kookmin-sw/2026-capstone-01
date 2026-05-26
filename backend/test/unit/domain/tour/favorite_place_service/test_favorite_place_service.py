"""FavoritePlaceService — 즐겨찾기 CRUD + RDB↔Mongo 합성 단위 테스트.

검증 대상:
    - `add_favorite`: 장소 검증 → 중복 가드 → INSERT
    - `remove_favorite`: 존재 가드 → DELETE
    - `get_favorites`: RDB 즐겨찾기 + Mongo 장소 batch + 순서 유지 + Mongo 결손 row skip
"""
from test.unit.domain.tour.place_service.model_factory import PlaceRawFactory
from test.unit.domain.tour.favorite_place_service.model_factory import FavoritePlaceFactory
import pytest


# ──────────────────────────────────────────────────────────────────
# add_favorite
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestAddFavorite:
    """Tests for FavoritePlaceService.add_favorite."""

    async def test_saves_favorite_when_place_exists_and_not_yet(
        self, service, place_repo_mock, fav_repo_mock,
    ):
        place_repo_mock.find_by_place_ids.return_value = [
            PlaceRawFactory.create(place_id="PLACE_x"),
        ]
        fav_repo_mock.find_by_user_and_place.return_value = None

        await service.add_favorite(user_id="USER_a", place_id="PLACE_x")

        fav_repo_mock.save.assert_awaited_once()
        saved = fav_repo_mock.save.await_args.args[0]
        assert saved.user_id == "USER_a"
        assert saved.place_id == "PLACE_x"


    async def test_raises_when_place_not_found(
        self, service, place_repo_mock, fav_repo_mock,
    ):
        place_repo_mock.find_by_place_ids.return_value = []

        with pytest.raises(ValueError, match="존재하지 않는 장소"):
            await service.add_favorite(user_id="USER_a", place_id="PLACE_x")

        fav_repo_mock.save.assert_not_awaited()


    async def test_raises_when_already_favorited(
        self, service, place_repo_mock, fav_repo_mock,
    ):
        place_repo_mock.find_by_place_ids.return_value = [PlaceRawFactory.create()]
        fav_repo_mock.find_by_user_and_place.return_value = FavoritePlaceFactory.create()

        with pytest.raises(ValueError, match="이미 즐겨찾기"):
            await service.add_favorite(user_id="USER_a", place_id="PLACE_x")

        fav_repo_mock.save.assert_not_awaited()


# ──────────────────────────────────────────────────────────────────
# remove_favorite
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRemoveFavorite:
    """Tests for FavoritePlaceService.remove_favorite."""

    async def test_deletes_existing_favorite(self, service, fav_repo_mock):
        fav_repo_mock.find_by_user_and_place.return_value = FavoritePlaceFactory.create()

        await service.remove_favorite(user_id="USER_a", place_id="PLACE_x")

        fav_repo_mock.delete_by_user_and_place.assert_awaited_once_with(
            "USER_a", "PLACE_x",
        )


    async def test_raises_when_not_favorited(self, service, fav_repo_mock):
        fav_repo_mock.find_by_user_and_place.return_value = None

        with pytest.raises(ValueError, match="즐겨찾기하지 않은"):
            await service.remove_favorite(user_id="USER_a", place_id="PLACE_x")

        fav_repo_mock.delete_by_user_and_place.assert_not_awaited()


# ──────────────────────────────────────────────────────────────────
# get_favorites — RDB 즐겨찾기 + Mongo 장소 batch
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetFavorites:
    """Tests for FavoritePlaceService.get_favorites."""

    async def test_returns_empty_when_no_favorites(
        self, service, fav_repo_mock, place_repo_mock,
    ):
        fav_repo_mock.find_all_by_user.return_value = []

        result = await service.get_favorites(user_id="USER_a")

        assert result.favorites == []
        assert result.total_count == 0
        # 빈 결과 → Mongo 조회 skip
        place_repo_mock.find_by_place_ids.assert_not_awaited()


    async def test_preserves_favorite_order(
        self, service, fav_repo_mock, place_repo_mock,
    ):
        """즐겨찾기 순서(최신순) 유지 — Mongo 응답 순서와 무관."""
        favorites = [
            FavoritePlaceFactory.create(favorite_id="FAV_1", place_id="P_1"),
            FavoritePlaceFactory.create(favorite_id="FAV_2", place_id="P_2"),
            FavoritePlaceFactory.create(favorite_id="FAV_3", place_id="P_3"),
        ]
        fav_repo_mock.find_all_by_user.return_value = favorites
        # Mongo 가 다른 순서로 반환해도 service 가 fav 순서대로 정렬
        place_repo_mock.find_by_place_ids.return_value = [
            PlaceRawFactory.create(place_id="P_3"),
            PlaceRawFactory.create(place_id="P_1"),
            PlaceRawFactory.create(place_id="P_2"),
        ]

        result = await service.get_favorites(user_id="USER_a")

        assert [f.favorite_id for f in result.favorites] == ["FAV_1", "FAV_2", "FAV_3"]
        assert [f.place.place_id for f in result.favorites] == ["P_1", "P_2", "P_3"]
        assert result.total_count == 3


    async def test_skips_favorite_when_place_missing_in_mongo(
        self, service, fav_repo_mock, place_repo_mock,
    ):
        """Mongo 에 place 결손 (운영 정합성 깨짐) — 해당 fav 응답에서 skip."""
        fav_repo_mock.find_all_by_user.return_value = [
            FavoritePlaceFactory.create(favorite_id="FAV_1", place_id="P_1"),
            FavoritePlaceFactory.create(favorite_id="FAV_2", place_id="P_missing"),
        ]
        place_repo_mock.find_by_place_ids.return_value = [
            PlaceRawFactory.create(place_id="P_1"),
        ]

        result = await service.get_favorites(user_id="USER_a")

        assert len(result.favorites) == 1
        assert result.favorites[0].favorite_id == "FAV_1"
        assert result.total_count == 1
