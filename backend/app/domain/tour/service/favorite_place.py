from app.domain.tour.service.place import PlaceService
from app.domain.tour.repository.place import PlaceRepository
from app.domain.tour.repository.favorite_place import FavoritePlaceRepository
from app.domain.tour.model.favorite_place import FavoritePlace
from app.domain.tour.dto.favorite_place import FavoritePlaceData, FavoritePlaceListData
from app.database.session import UnitOfWork, transactional


class FavoritePlaceService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow
        self.place_repo = PlaceRepository()

    # ──────────────────── 즐겨찾기 추가 ────────────────────

    @transactional
    async def add_favorite(self, user_id: str, place_id: str) -> None:
        """
        장소 즐겨찾기 추가

        1. MongoDB에서 장소 존재 검증
        2. 이미 즐겨찾기한 장소인지 확인 (중복 방지)
        3. 즐겨찾기 저장
        """
        # 장소 존재 검증
        places = await self.place_repo.find_by_place_ids([place_id])
        if not places:
            raise ValueError("존재하지 않는 장소입니다.")

        fav_repo = FavoritePlaceRepository(self._session)

        existing = await fav_repo.find_by_user_and_place(user_id, place_id)
        if existing is not None:
            raise ValueError("이미 즐겨찾기한 장소입니다.")

        favorite = FavoritePlace(user_id=user_id, place_id=place_id)
        await fav_repo.save(favorite)

    # ──────────────────── 즐겨찾기 삭제 ────────────────────

    @transactional
    async def remove_favorite(self, user_id: str, place_id: str) -> None:
        """
        장소 즐겨찾기 해제

        1. 즐겨찾기 존재 검증
        2. 삭제
        """
        fav_repo = FavoritePlaceRepository(self._session)

        existing = await fav_repo.find_by_user_and_place(user_id, place_id)
        if existing is None:
            raise ValueError("즐겨찾기하지 않은 장소입니다.")

        await fav_repo.delete_by_user_and_place(user_id, place_id)

    # ──────────────────── 즐겨찾기 목록 조회 ────────────────────

    @transactional
    async def get_favorites(self, user_id: str) -> FavoritePlaceListData:
        """
        유저의 즐겨찾기 목록 조회 (최신순, 장소 상세 포함)

        1. RDB에서 즐겨찾기 목록 조회
        2. MongoDB에서 place_id 배치 조회
        3. 즐겨찾기 순서 유지하며 장소 상세 병합
        """
        fav_repo = FavoritePlaceRepository(self._session)

        favorites = await fav_repo.find_all_by_user(user_id)
        if not favorites:
            return FavoritePlaceListData(favorites=[], total_count=0)

        # MongoDB 배치 조회 → place_id로 인덱싱
        place_ids = [f.place_id for f in favorites]
        raw_places = await self.place_repo.find_by_place_ids(place_ids)
        place_map = {p["place_id"]: p for p in raw_places}

        # 즐겨찾기 순서(최신순) 유지하며 병합
        result = []
        for fav in favorites:
            raw = place_map.get(fav.place_id)
            if raw is None:
                continue
            result.append(FavoritePlaceData(
                favorite_id=fav.favorite_id,
                created_at=fav.created_at,
                place=PlaceService.to_detail_dto(raw),
            ))

        return FavoritePlaceListData(favorites=result, total_count=len(result))
