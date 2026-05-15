"""PlaceService 단위 테스트용 raw dict 팩토리.

`PlaceRepository` 의 모든 메서드는 Mongo raw dict 를 반환한다 (model 변환 안 함). service
의 `_build_common_fields` / `_to_dto` 가 dict 키를 직접 참조하므로 테스트도 같은 형태로
입력을 합성. pydantic DTO 검증을 통과할 만큼 필수 필드를 채운다.

`category` 는 영어 (예: "restaurant") — `Place` model 컨벤션 (한글 description 이지만
실제 DB 값은 영어).
"""
from typing import Optional


class PlaceRawFactory:
    _counter = 0

    @classmethod
    def create(
        cls,
        *,
        place_id: Optional[str] = None,
        display_name: str = "Test Place",
        category: str = "restaurant",
        address: str = "Seoul",
        lat: float = 37.5,
        lng: float = 127.0,
        distance: float = 100.0,
        **extra,
    ) -> dict:
        cls._counter += 1
        raw = {
            "place_id": place_id or f"PLACE_test_{cls._counter:04d}",
            "display_name": display_name,
            "category": category,
            "types": [],
            "address": address,
            "short_address": None,
            "location": {"coordinates": [lng, lat]},  # GeoJSON: [lng, lat]
            "distance": distance,
            "rating": None,
            "rating_count": None,
            "price_level": None,
            "price_range": None,
            "editorial_summary": None,
            "generative_summary": None,
            "review_summary": None,
            "phone": None,
            "phone_international": None,
            "website": None,
            "google_maps_url": None,
            "google_map_review_link": None,
            "opening_hours": None,
            "services": None,
            "payment": None,
            "accessibility": None,
            "parking": None,
            "reviews": [],
            "photos": [],
        }
        raw.update(extra)
        return raw

    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0
