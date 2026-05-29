"""TripmateImageService 단위 테스트용 도메인 객체 팩토리.

`TripmateImage` 는 `find_by_user_id` / `find_by_image_id` 응답이며 service 가 `image_id`,
`user_id`, `image_url` attribute 만 접근. SimpleNamespace minimal stub.
"""
from typing import Optional
from types import SimpleNamespace


class TripmateImageFactory:
    _counter = 0

    @classmethod
    def create(
        cls,
        *,
        image_id: Optional[str] = None,
        user_id: str = "USER_owner",
        image_url: Optional[str] = None,
    ) -> SimpleNamespace:
        cls._counter += 1
        image_id_val = image_id or f"IMG_test_{cls._counter:04d}"
        return SimpleNamespace(
            image_id=image_id_val,
            user_id=user_id,
            image_url=image_url or f"https://img/{image_id_val}.jpg",
        )


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0
