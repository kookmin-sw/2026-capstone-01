"""TripmatePostLikeService 단위 테스트용 도메인 객체 팩토리.

SQLAlchemy 모델을 직접 인스턴스화하면 backref 이벤트가 `_sa_instance_state` 를 요구해
에러가 나므로, friend / notification 도메인 컨벤션 동일하게 `SimpleNamespace` 로 attribute
만 흉내내는 팩토리를 제공한다. service 의 `_add_like_tx` 가 접근하는 `post.user_id`,
`post.title`, `detail.user_name`, `detail.profile_image_url` 만 채우면 충분.
"""
from typing import Optional
from types import SimpleNamespace
from datetime import datetime, timezone


class TripmatePostFactory:
    _counter = 0

    @classmethod
    def create(
        cls,
        *,
        post_id: Optional[str] = None,
        user_id: str = "USER_owner",
        title: str = "여행 같이 가실 분",
    ) -> SimpleNamespace:
        cls._counter += 1
        return SimpleNamespace(
            post_id=post_id or f"TMP_test_{cls._counter:04d}",
            user_id=user_id,
            title=title,
        )


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0


class UserDetailInformFactory:
    """fan-out 시점의 actor snapshot 합성 입력 — `user_name` / `profile_image_url` 만 사용."""

    _counter = 0

    @classmethod
    def create(
        cls,
        *,
        user_id: str = "USER_actor",
        user_name: str = "actorName",
        profile_image_url: Optional[str] = None,
    ) -> SimpleNamespace:
        cls._counter += 1
        return SimpleNamespace(
            user_id=user_id,
            user_name=user_name,
            profile_image_url=profile_image_url,
        )


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0
