"""RegisterService — 2차 회원가입 (UserDetailInform + UserTravelStyle 합성) 단위 테스트.

검증 대상:
    - 정상 흐름: detail save + travel_styles save_all (1회씩)
    - 가드: user 미존재 → ValueError, detail 이미 존재 (중복 가입) → ValueError
    - 인자 검증: detail 의 모든 field 가 입력대로 매핑
    - 빈 travel_styles 도 허용 (save_all 빈 리스트 호출)
"""
from test.unit.domain.auth.register_service.model_factory import (
    UserDetailInformFactory,
    UserFactory,
)
import pytest

from app.domain.auth.model.user_travel_style import TravelStyle
from app.domain.auth.model.user_detail_inform import Gender


def _kwargs_baseline(**overrides):
    """register_detail 의 공통 baseline kwargs — 개별 테스트가 일부만 override."""
    base = {
        "user_id": "USER_a",
        "email": "a@example.com",
        "user_name": "조현상",
        "phone_number": "010-0000-0000",
        "age": 25,
        "gender": Gender.MALE,
        "nationality": "KR",
        "travel_styles": [TravelStyle.ACTIVITY, TravelStyle.HEALING],
    }
    base.update(overrides)
    return base


@pytest.mark.unit
class TestRegisterDetail:
    """Tests for RegisterService.register_detail."""

    async def test_saves_detail_and_travel_styles(
        self, service, user_repo_mock, detail_repo_mock, style_repo_mock,
    ):
        user_repo_mock.find_by_id.return_value = UserFactory.create(user_id="USER_a")
        detail_repo_mock.find_by_user_id.return_value = None  # 미가입

        await service.register_detail(**_kwargs_baseline())

        detail_repo_mock.save.assert_awaited_once()
        style_repo_mock.save_all.assert_awaited_once()


    async def test_detail_fields_mapped_correctly(
        self, service, user_repo_mock, detail_repo_mock,
    ):
        """detail save 인자 검증 — 입력 field 가 모두 매핑."""
        user_repo_mock.find_by_id.return_value = UserFactory.create(user_id="USER_a")
        detail_repo_mock.find_by_user_id.return_value = None

        await service.register_detail(**_kwargs_baseline(
            email="custom@e.com",
            user_name="홍길동",
            age=30,
            gender=Gender.FEMALE,
            nationality="JP",
        ))

        saved_detail = detail_repo_mock.save.await_args.args[0]
        assert saved_detail.user_id == "USER_a"
        assert saved_detail.email == "custom@e.com"
        assert saved_detail.user_name == "홍길동"
        assert saved_detail.age == 30
        assert saved_detail.gender == Gender.FEMALE
        assert saved_detail.nationality == "JP"


    async def test_saves_multiple_travel_styles(
        self, service, user_repo_mock, detail_repo_mock, style_repo_mock,
    ):
        """N 개 travel_styles → N 개 UserTravelStyle row 합성."""
        user_repo_mock.find_by_id.return_value = UserFactory.create(user_id="USER_a")
        detail_repo_mock.find_by_user_id.return_value = None

        styles_input = [TravelStyle.ACTIVITY, TravelStyle.HEALING, TravelStyle.SHOPPING]
        await service.register_detail(**_kwargs_baseline(travel_styles=styles_input))

        saved_styles = style_repo_mock.save_all.await_args.args[0]
        assert len(saved_styles) == 3
        assert [s.style for s in saved_styles] == styles_input
        assert all(s.user_id == "USER_a" for s in saved_styles)


    async def test_saves_empty_travel_styles(
        self, service, user_repo_mock, detail_repo_mock, style_repo_mock,
    ):
        """빈 travel_styles — save_all 호출되지만 빈 리스트."""
        user_repo_mock.find_by_id.return_value = UserFactory.create(user_id="USER_a")
        detail_repo_mock.find_by_user_id.return_value = None

        await service.register_detail(**_kwargs_baseline(travel_styles=[]))

        style_repo_mock.save_all.assert_awaited_once_with([])


    async def test_raises_when_user_not_found(
        self, service, user_repo_mock, detail_repo_mock, style_repo_mock,
    ):
        user_repo_mock.find_by_id.return_value = None

        with pytest.raises(ValueError, match="존재하지 않는"):
            await service.register_detail(**_kwargs_baseline())

        detail_repo_mock.save.assert_not_awaited()
        style_repo_mock.save_all.assert_not_awaited()


    async def test_raises_when_already_registered(
        self, service, user_repo_mock, detail_repo_mock, style_repo_mock,
    ):
        """detail 이미 존재 → 중복 가입 차단."""
        user_repo_mock.find_by_id.return_value = UserFactory.create(user_id="USER_a")
        detail_repo_mock.find_by_user_id.return_value = UserDetailInformFactory.create(
            user_id="USER_a",
        )

        with pytest.raises(ValueError, match="이미 2차 회원가입"):
            await service.register_detail(**_kwargs_baseline())

        detail_repo_mock.save.assert_not_awaited()
        style_repo_mock.save_all.assert_not_awaited()
