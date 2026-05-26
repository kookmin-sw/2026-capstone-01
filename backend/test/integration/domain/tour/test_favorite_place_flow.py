"""FavoritePlaceService — RDB 즐겨찾기 + Mongo 장소 합성 e2e 통합 테스트.

unit 으로 검증 못 하는 영역:
    - place 미존재 가드 — Mongo `find_by_place_ids` 가 RDB INSERT 전에 차단
    - composite UNIQUE (user_id, place_id) — 중복 add 차단
    - get_favorites 의 RDB↔Mongo 합성 — 즐겨찾기 순서 유지 + Mongo 결손 row skip

검증 매트릭스:

    | 시나리오                          | 기대                                |
    |---|---|
    | add 정상                         | RDB INSERT + 응답                    |
    | add place 미존재                 | ValueError (Mongo 검증 단계)          |
    | add 중복                         | ValueError (RDB pre-check)           |
    | remove 미존재                    | ValueError                           |
    | get_favorites 순서 유지          | RDB 최신순 그대로                    |
    | get_favorites Mongo 결손         | 해당 row skip (전체는 통과)          |
"""
from sqlalchemy import select
import pytest

from app.domain.tour.model.place import Place
from app.domain.tour.model.favorite_place import FavoritePlace


pytestmark = pytest.mark.integration


# ──────────────────── add_favorite ────────────────────

class TestAddFavorite:
    async def test_persists_when_place_exists(
        self, favorite_place_service, seed_users, seed_place, session_factory,
    ):
        [user_id] = await seed_users(1)
        place_id = await seed_place(place_id="PLACE_x")

        await favorite_place_service.add_favorite(user_id=user_id, place_id=place_id)

        async with session_factory() as session:
            result = await session.execute(
                select(FavoritePlace).where(FavoritePlace.user_id == user_id)
            )
            favorites = list(result.scalars().all())
            assert len(favorites) == 1
            assert favorites[0].place_id == place_id


    async def test_raises_when_place_not_found_in_mongo(
        self, favorite_place_service, seed_users, session_factory,
    ):
        """Mongo 에 place 없으면 RDB INSERT 도달 X — 잘못된 place_id 방어."""
        [user_id] = await seed_users(1)

        with pytest.raises(ValueError, match="존재하지 않는 장소"):
            await favorite_place_service.add_favorite(
                user_id=user_id, place_id="PLACE_ghost",
            )

        # RDB 에 INSERT 안 됨
        async with session_factory() as session:
            result = await session.execute(select(FavoritePlace))
            assert list(result.scalars().all()) == []


    async def test_raises_when_already_favorited(
        self, favorite_place_service, seed_users, seed_place,
    ):
        [user_id] = await seed_users(1)
        place_id = await seed_place(place_id="PLACE_x")

        await favorite_place_service.add_favorite(user_id=user_id, place_id=place_id)

        with pytest.raises(ValueError, match="이미 즐겨찾기"):
            await favorite_place_service.add_favorite(
                user_id=user_id, place_id=place_id,
            )


# ──────────────────── remove_favorite ────────────────────

class TestRemoveFavorite:
    async def test_deletes_existing(
        self, favorite_place_service, seed_users, seed_place, session_factory,
    ):
        [user_id] = await seed_users(1)
        place_id = await seed_place(place_id="PLACE_x")
        await favorite_place_service.add_favorite(user_id=user_id, place_id=place_id)

        await favorite_place_service.remove_favorite(
            user_id=user_id, place_id=place_id,
        )

        async with session_factory() as session:
            result = await session.execute(select(FavoritePlace))
            assert list(result.scalars().all()) == []


    async def test_raises_when_not_favorited(
        self, favorite_place_service, seed_users,
    ):
        [user_id] = await seed_users(1)

        with pytest.raises(ValueError, match="즐겨찾기하지 않은"):
            await favorite_place_service.remove_favorite(
                user_id=user_id, place_id="PLACE_ghost",
            )


# ──────────────────── get_favorites — RDB↔Mongo 합성 ────────────────────

class TestGetFavorites:
    async def test_preserves_recent_first_order(
        self, favorite_place_service, seed_users, seed_place,
    ):
        [user_id] = await seed_users(1)
        # 3개 place 시드
        p1 = await seed_place(place_id="P_1", display_name="First")
        p2 = await seed_place(place_id="P_2", display_name="Second")
        p3 = await seed_place(place_id="P_3", display_name="Third")

        # 즐겨찾기 순서대로 추가 (P_1 → P_2 → P_3)
        await favorite_place_service.add_favorite(user_id=user_id, place_id=p1)
        await favorite_place_service.add_favorite(user_id=user_id, place_id=p2)
        await favorite_place_service.add_favorite(user_id=user_id, place_id=p3)

        result = await favorite_place_service.get_favorites(user_id=user_id)

        # 최신순 — P_3 가 첫 번째
        place_ids = [f.place.place_id for f in result.favorites]
        assert place_ids == ["P_3", "P_2", "P_1"]
        assert result.total_count == 3


    async def test_skips_favorite_when_place_missing_in_mongo(
        self, favorite_place_service, seed_users, seed_place, session_factory,
    ):
        """Mongo 에서 place 가 사라진 favorite 은 응답에서 skip — 운영 정합성 깨짐 방어."""
        [user_id] = await seed_users(1)
        p1 = await seed_place(place_id="P_alive")
        p2 = await seed_place(place_id="P_will_disappear")

        await favorite_place_service.add_favorite(user_id=user_id, place_id=p1)
        await favorite_place_service.add_favorite(user_id=user_id, place_id=p2)

        # Mongo 에서 P_will_disappear 만 직접 삭제 (RDB favorite 은 잔존)
        coll = Place.get_motor_collection()
        await coll.delete_one({"place_id": "P_will_disappear"})

        result = await favorite_place_service.get_favorites(user_id=user_id)

        # Mongo 결손 row 는 skip — total_count = 매칭된 1건
        assert result.total_count == 1
        assert result.favorites[0].place.place_id == "P_alive"


    async def test_returns_empty_when_no_favorites(
        self, favorite_place_service, seed_users,
    ):
        [user_id] = await seed_users(1)

        result = await favorite_place_service.get_favorites(user_id=user_id)

        assert result.favorites == []
        assert result.total_count == 0
