"""TripmatePostService 단위 테스트용 도메인 객체 팩토리.

`_to_dto` 가 접근하는 attribute 가 많아 (post.user.detail.* / post.like_count / post.is_liked /
post.images / sorted(images, key=image_order)), `SimpleNamespace` 합성으로 다 채운다.
`find_by_id_with_detail` 는 동적으로 `like_count` / `is_liked` 를 post 객체에 부여하는
패턴을 시뮬레이션 — factory 가 같은 형태로 빌드.
"""
from typing import List, Optional
from types import SimpleNamespace
from datetime import date, datetime, timezone

from app.domain.tripmate.model.tripmate_post import CompanionType, PreferredGender
from app.domain.auth.model.user_detail_inform import Gender


class TripmatePostFactory:
    _counter = 0

    @classmethod
    def create(
        cls,
        *,
        post_id: Optional[str] = None,
        user_id: str = "USER_owner",
        title: str = "여행 같이 가실 분",
        content: str = "이번 주말 제주 동행 구합니다",
        preferred_age_min: int = 20,
        preferred_age_max: int = 30,
        preferred_gender: PreferredGender = PreferredGender.ANY,
        region: str = "제주",
        travel_start_date: date = date(2026, 6, 1),
        travel_end_date: date = date(2026, 6, 5),
        companion_type: CompanionType = CompanionType.FRIEND,
        is_displayed: bool = True,
        # `_to_dto` 가 동적으로 접근하는 attribute (find_by_id_with_detail 시뮬레이션)
        like_count: int = 0,
        is_liked: bool = False,
        images: Optional[List[SimpleNamespace]] = None,
        # author profile (post.user.detail)
        author_name: str = "조현상",
        author_age: int = 25,
        author_gender: Gender = Gender.MALE,
        author_nationality: str = "KR",
        author_profile_image_url: Optional[str] = None,
        author_detail_present: bool = True,
    ) -> SimpleNamespace:
        cls._counter += 1
        post_id_val = post_id or f"TMP_test_{cls._counter:04d}"

        user = SimpleNamespace(user_id=user_id)
        if author_detail_present:
            user.detail = SimpleNamespace(
                user_id=user_id,
                user_name=author_name,
                age=author_age,
                gender=author_gender,
                nationality=author_nationality,
                profile_image_url=author_profile_image_url,
            )
        else:
            user.detail = None

        return SimpleNamespace(
            post_id=post_id_val,
            user_id=user_id,
            title=title,
            content=content,
            preferred_age_min=preferred_age_min,
            preferred_age_max=preferred_age_max,
            preferred_gender=preferred_gender,
            region=region,
            travel_start_date=travel_start_date,
            travel_end_date=travel_end_date,
            companion_type=companion_type,
            is_displayed=is_displayed,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            user=user,
            like_count=like_count,
            is_liked=is_liked,
            images=images if images is not None else [],
        )


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0


def make_post_image(image_url: str, image_order: int = 0) -> SimpleNamespace:
    """`TripmatePostImage` 흉내 — `find_by_post_id` 결과 row."""
    return SimpleNamespace(image_url=image_url, image_order=image_order)
