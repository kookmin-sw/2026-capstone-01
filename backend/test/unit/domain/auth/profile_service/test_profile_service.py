"""ProfileService.get_my_profile 단위 테스트.

핵심 검증:
    - 응답에 `notification_muted` 가 노출되며 DB True/NULL/False 가 깔끔한 bool 로 coerce
      (`is True` 기준 — 가드 비교 연산자와 일관)
    - detail 분기 (없으면 ProfileNotRegisteredError)
    - 존재하지 않는 user → ValueError
    - 정상 케이스에서 다른 프로필 필드도 1:1 매핑 (스모크)

이미지 CRUD 메서드(`add/update/delete_profile_image`) 는 본 모듈 범위 밖.
"""
from types import SimpleNamespace
import pytest

from app.domain.auth.service.exception import ProfileNotRegisteredError
from app.domain.auth.model.user_travel_style import TravelStyle
from app.domain.auth.model.user_detail_inform import Gender
from app.domain.auth.model.user import UserStatus
from app.config.oauth import OAuthProvider


def _mk_user(
    *,
    user_id: str = "USER_a",
    notification_muted=None,
    detail=None,
    travel_styles=None,
) -> SimpleNamespace:
    """User ORM 객체 흉내 — service 가 접근하는 속성만 채움."""
    return SimpleNamespace(
        user_id=user_id,
        auth_provider=OAuthProvider.GOOGLE,
        status=UserStatus.ACTIVE,
        notification_muted=notification_muted,
        detail=detail,
        travel_styles=travel_styles or [],
    )


def _mk_detail(
    *,
    email: str = "u@example.com",
    user_name: str = "조현상",
    phone_number: str = "010-1234-5678",
    age: int = 26,
    gender: Gender = Gender.MALE,
    nationality: str = "korea",
    profile_image_url: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        email=email,
        user_name=user_name,
        phone_number=phone_number,
        age=age,
        gender=gender,
        nationality=nationality,
        profile_image_url=profile_image_url,
    )


def _mk_travel_style(style: TravelStyle) -> SimpleNamespace:
    return SimpleNamespace(style=style)


# ──────────────────────────────────────────────────────────────────
# notification_muted 노출 — 핵심 회귀 검증
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestNotificationMutedExposure:
    async def test_mute_true_exposed_as_true(self, service, user_repo_mock):
        user_repo_mock.find_by_id_with_profile.return_value = _mk_user(
            notification_muted=True, detail=_mk_detail(),
        )

        result = await service.get_my_profile("USER_a")
        assert result.notification_muted is True


    async def test_mute_null_normalizes_to_false(self, service, user_repo_mock):
        """기본 unmuted (DB NULL) → 응답에선 False — 클라가 null 분기 안 해도 됨."""
        user_repo_mock.find_by_id_with_profile.return_value = _mk_user(
            notification_muted=None, detail=_mk_detail(),
        )

        result = await service.get_my_profile("USER_a")
        assert result.notification_muted is False


    async def test_mute_false_treated_as_unmuted(self, service, user_repo_mock):
        """레거시/이상치 False 도 `is True` 비교라 False — FCM 가드 컨벤션과 일관."""
        user_repo_mock.find_by_id_with_profile.return_value = _mk_user(
            notification_muted=False, detail=_mk_detail(),
        )

        result = await service.get_my_profile("USER_a")
        assert result.notification_muted is False


# ──────────────────────────────────────────────────────────────────
# 권한 / 분기
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetMyProfileBranches:
    async def test_nonexistent_user_raises_value_error(
        self, service, user_repo_mock,
    ):
        user_repo_mock.find_by_id_with_profile.return_value = None

        with pytest.raises(ValueError, match="존재하지 않는"):
            await service.get_my_profile("USER_x")


    async def test_user_without_detail_raises_profile_not_registered(
        self, service, user_repo_mock,
    ):
        """2차 회원가입 미완 — detail 누락 시 명시적 에러로 회원가입 단계 분기."""
        user_repo_mock.find_by_id_with_profile.return_value = _mk_user(
            detail=None,
        )

        with pytest.raises(ProfileNotRegisteredError):
            await service.get_my_profile("USER_a")


# ──────────────────────────────────────────────────────────────────
# 필드 매핑 스모크
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestProfileFieldMapping:
    async def test_all_fields_mapped_correctly(self, service, user_repo_mock):
        user_repo_mock.find_by_id_with_profile.return_value = _mk_user(
            user_id="USER_smoke",
            notification_muted=True,
            detail=_mk_detail(
                email="me@example.com",
                user_name="홍길동",
                phone_number="010-9999-9999",
                age=30,
                gender=Gender.FEMALE,
                nationality="korea",
                profile_image_url="https://cdn.example.com/me.jpg",
            ),
            travel_styles=[
                _mk_travel_style(TravelStyle.ACTIVITY),
                _mk_travel_style(TravelStyle.FOOD_TOUR),
            ],
        )

        result = await service.get_my_profile("USER_smoke")

        assert result.user_id == "USER_smoke"
        assert result.auth_provider == OAuthProvider.GOOGLE
        assert result.status == UserStatus.ACTIVE
        assert result.email == "me@example.com"
        assert result.user_name == "홍길동"
        assert result.phone_number == "010-9999-9999"
        assert result.age == 30
        assert result.gender == Gender.FEMALE
        assert result.nationality == "korea"
        assert result.profile_image_url == "https://cdn.example.com/me.jpg"
        assert result.travel_styles == [TravelStyle.ACTIVITY, TravelStyle.FOOD_TOUR]
        assert result.notification_muted is True


    async def test_empty_travel_styles_returns_empty_list(
        self, service, user_repo_mock,
    ):
        user_repo_mock.find_by_id_with_profile.return_value = _mk_user(
            detail=_mk_detail(),
            travel_styles=[],
        )

        result = await service.get_my_profile("USER_a")
        assert result.travel_styles == []


    async def test_no_profile_image_returns_none(self, service, user_repo_mock):
        user_repo_mock.find_by_id_with_profile.return_value = _mk_user(
            detail=_mk_detail(profile_image_url=None),
        )

        result = await service.get_my_profile("USER_a")
        assert result.profile_image_url is None


# ──────────────────── get_my_stats ────────────────────

@pytest.mark.unit
class TestGetMyStats:
    """마이페이지 통계 — 본인 피드 좋아요 총 합 + ACCEPTED 친구 수.

    cross-domain 카운터 두 개를 단일 트랜잭션에서 조합. service↔repo 경계에서 user_id 가
    정확히 전달되고 응답 DTO 매핑이 두 카운트를 정확히 노출해야 함.
    """
    async def test_user_not_found_raises_value_error(self, service, user_repo_mock):
        """존재하지 않는 user_id → ValueError (라우터에서 404 매핑)."""
        user_repo_mock.find_by_id.return_value = None

        with pytest.raises(ValueError):
            await service.get_my_stats("USER_ghost")


    async def test_returns_zero_counts_when_no_activity(
        self, service, user_repo_mock, feed_post_like_repo_mock, friendship_repo_mock,
    ):
        """좋아요/친구 0건 — DTO 의 두 필드 모두 0 노출."""
        user_repo_mock.find_by_id.return_value = object()  # 존재만 검증
        feed_post_like_repo_mock.count_total_for_owner.return_value = 0
        friendship_repo_mock.count_accepted_for.return_value = 0

        result = await service.get_my_stats("USER_a")

        assert result.total_feed_likes == 0
        assert result.total_friends == 0


    async def test_propagates_counts_from_repos(
        self, service, user_repo_mock, feed_post_like_repo_mock, friendship_repo_mock,
    ):
        """repo 가 반환한 값이 DTO 까지 정확히 흘러가는지 — _to_dto 누락 회귀 가드."""
        user_repo_mock.find_by_id.return_value = object()
        feed_post_like_repo_mock.count_total_for_owner.return_value = 42
        friendship_repo_mock.count_accepted_for.return_value = 7

        result = await service.get_my_stats("USER_a")

        assert result.total_feed_likes == 42
        assert result.total_friends == 7


    async def test_forwards_user_id_to_both_repos(
        self, service, user_repo_mock, feed_post_like_repo_mock, friendship_repo_mock,
    ):
        """user_id 가 두 repo 모두에 정확히 전달돼야 다른 유저의 카운트가 누출되지 않음."""
        user_repo_mock.find_by_id.return_value = object()

        await service.get_my_stats("USER_xyz")

        assert feed_post_like_repo_mock.count_total_for_owner.await_args.args == ("USER_xyz",)
        assert friendship_repo_mock.count_accepted_for.await_args.args == ("USER_xyz",)


    async def test_does_not_require_detail_row(
        self, service, user_repo_mock, feed_post_like_repo_mock, friendship_repo_mock,
    ):
        """detail (2차 회원가입) 결손이어도 stats 는 조회 가능 — 좋아요/친구는 detail 무관."""
        # find_by_id 만 호출하므로 detail 검증 자체가 없음 — 회귀 가드.
        user_repo_mock.find_by_id.return_value = object()
        feed_post_like_repo_mock.count_total_for_owner.return_value = 1
        friendship_repo_mock.count_accepted_for.return_value = 2

        # ProfileNotRegisteredError 가 발생하지 않아야 함.
        result = await service.get_my_stats("USER_no_detail")
        assert result.total_feed_likes == 1
        assert result.total_friends == 2
