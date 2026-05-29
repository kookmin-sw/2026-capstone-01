from app.domain.tour.repository.place import PlaceRepository, PAGE_SIZE
from app.domain.tour.repository.favorite_place import FavoritePlaceRepository
from app.domain.tour.dto.place import (
    PlaceDetailData,
    PlaceData,
    PlaceListData,
    PlaceLocationData,
    PlacePriceRangeData,
    PlaceReviewData,
)
from app.database.session import UnitOfWork, transactional


class PlaceService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow
        self.place_repo = PlaceRepository()

    # ──────────────────── 거리순 장소 조회 ────────────────────

    @transactional
    async def get_nearby_places(
        self,
        lat: float,
        lng: float,
        cursor: str | None = None,
        max_distance: float | None = None,
        user_id: str = "",
    ) -> PlaceListData:
        """현재 위치 기준 가까운 장소 목록 조회 (거리순, 30개 페이지네이션)"""
        places = await self.place_repo.find_nearby(lat, lng, cursor=cursor, max_distance=max_distance)
        favorited = await self._get_favorited_set(places, user_id)
        return self._to_list_dto(places, favorited)

    # ──────────────────── place_id 단건 조회 ────────────────────

    @transactional
    async def get_place_by_id(
        self,
        place_id: str,
        user_id: str = "",
    ) -> PlaceData | None:
        """place_id로 장소 단건 조회"""
        raw = await self.place_repo.find_by_place_id(place_id)
        if raw is None:
            return None
        favorited = await self._get_favorited_set([raw], user_id)
        return self._to_dto(raw, favorited)

    # ──────────────────── 키워드 검색 + 거리순 ────────────────────

    @transactional
    async def search_nearby_places(
        self,
        lat: float,
        lng: float,
        keyword: str,
        cursor: str | None = None,
        max_distance: float | None = None,
        user_id: str = "",
    ) -> PlaceListData:
        """키워드 검색 + 거리순 정렬 (display_name, category 매칭)"""
        places = await self.place_repo.search_nearby(lat, lng, keyword, cursor=cursor, max_distance=max_distance)
        favorited = await self._get_favorited_set(places, user_id)
        return self._to_list_dto(places, favorited)

    # ──────────────────── 즐겨찾기 배치 조회 ────────────────────

    async def _get_favorited_set(self, places: list[dict], user_id: str) -> set[str]:
        """유저의 즐겨찾기 place_id set 반환"""
        if not user_id or not places:
            return set()
        fav_repo = FavoritePlaceRepository(self._session)
        place_ids = [p["place_id"] for p in places]
        return await fav_repo.find_favorited_place_ids(user_id, place_ids)

    # ──────────────────── 내부 변환 유틸 ────────────────────

    def _to_list_dto(self, places: list[dict], favorited: set[str]) -> PlaceListData:
        """raw dict 목록 → PlaceListData 변환 + 다음 커서 생성"""
        place_dtos = [self._to_dto(p, favorited) for p in places]

        next_cursor = None
        if len(places) == PAGE_SIZE:
            last = places[-1]
            next_cursor = PlaceRepository.build_cursor(last["distance"], last["place_id"])

        return PlaceListData(places=place_dtos, next_cursor=next_cursor)


    @staticmethod
    def _build_common_fields(raw: dict) -> dict:
        """MongoDB raw dict → 공통 필드 dict 변환"""
        coords = raw.get("location", {}).get("coordinates", [0.0, 0.0])

        pr = raw.get("price_range")

        return dict(
            place_id=raw["place_id"],
            display_name=raw["display_name"],
            category=raw["category"],
            types=raw.get("types", []),
            address=raw["address"],
            short_address=raw.get("short_address"),
            location=PlaceLocationData(lat=coords[1], lng=coords[0]),
            rating=raw.get("rating"),
            rating_count=raw.get("rating_count"),
            price_level=raw.get("price_level"),
            price_range=PlacePriceRangeData(min=pr.get("min"), max=pr.get("max")) if pr else None,
            editorial_summary=raw.get("editorial_summary"),
            generative_summary=raw.get("generative_summary"),
            review_summary=raw.get("review_summary"),
            phone=raw.get("phone"),
            phone_international=raw.get("phone_international"),
            website=raw.get("website"),
            google_maps_url=raw.get("google_maps_url"),
            google_map_review_link=raw.get("google_map_review_link"),
            opening_hours=raw.get("opening_hours"),
            services=raw.get("services"),
            payment=raw.get("payment"),
            accessibility=raw.get("accessibility"),
            parking=raw.get("parking"),
            reviews=[
                PlaceReviewData(
                    author=r.get("author", ""),
                    rating=r.get("rating"),
                    relative_time=r.get("relative_time"),
                    text=r.get("text"),
                )
                for r in (raw.get("reviews") or [])
            ],
            photos=raw.get("photos") or [],
        )


    @staticmethod
    def to_detail_dto(raw: dict) -> PlaceDetailData:
        """MongoDB raw dict → PlaceDetailData DTO 변환 (장소 상세만)"""
        return PlaceDetailData(**PlaceService._build_common_fields(raw))


    @staticmethod
    def _to_dto(raw: dict, favorited: set[str]) -> PlaceData:
        """MongoDB raw dict → PlaceData DTO 변환 (거리 + 즐겨찾기 포함)"""
        is_favorite = True if raw["place_id"] in favorited else None
        return PlaceData(
            **PlaceService._build_common_fields(raw),
            distance=raw.get("distance", 0.0),
            is_favorite=is_favorite,
        )
