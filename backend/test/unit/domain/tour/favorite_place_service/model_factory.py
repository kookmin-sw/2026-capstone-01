"""FavoritePlaceService 단위 테스트용 도메인 객체 팩토리.

`FavoritePlace` 는 RDB row — service 가 `favorite_id`, `created_at`, `place_id`, `user_id`
attribute 만 접근. SimpleNamespace 로 minimal stub.
"""
from typing import Optional
from types import SimpleNamespace
from datetime import datetime, timezone


class FavoritePlaceFactory:
    _counter = 0

    @classmethod
    def create(
        cls,
        *,
        favorite_id: Optional[str] = None,
        user_id: str = "USER_a",
        place_id: str = "PLACE_x",
        created_at: Optional[datetime] = None,
    ) -> SimpleNamespace:
        cls._counter += 1
        return SimpleNamespace(
            favorite_id=favorite_id or f"FAV_test_{cls._counter:04d}",
            user_id=user_id,
            place_id=place_id,
            created_at=created_at or datetime.now(timezone.utc),
        )


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0
