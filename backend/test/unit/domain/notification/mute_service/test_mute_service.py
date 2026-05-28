"""MuteService — 전역(유저) / 방별(멤버) 알림 차단 토글 단위 테스트.

저장 정규화 규칙 검증: True 만 row 에 적고 False 는 NULL 로 되돌린다.
"""
import pytest

from app.domain.chat.model.chat_room_member import ChatRoomMember
from app.domain.auth.model.user import User


def _make_user(user_id: str, *, notification_muted=None) -> User:
    """SQLAlchemy 모델 직접 인스턴스화 (DB 없이)."""
    u = User()
    u.user_id = user_id
    u.notification_muted = notification_muted
    return u


def _make_member(
    chat_room_id: str, user_id: str, *,
    is_left: bool = False,
    notification_muted=None,
) -> ChatRoomMember:
    m = ChatRoomMember()
    m.chat_room_id = chat_room_id
    m.user_id = user_id
    m.is_left = is_left
    m.notification_muted = notification_muted
    return m


# ──────────────────────────────────────────────────────────────────
# set_global_mute — 전역 차단 토글
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSetGlobalMute:
    async def test_muted_true_writes_true_and_calls_update(
        self, service, user_repo_mock,
    ):
        user = _make_user("USER_a", notification_muted=None)
        user_repo_mock.find_by_id.return_value = user

        await service.set_global_mute(user_id="USER_a", muted=True)

        assert user.notification_muted is True
        user_repo_mock.update.assert_awaited_once_with(user)


    async def test_muted_false_normalizes_to_none(
        self, service, user_repo_mock,
    ):
        """저장 정규화: False 입력 → DB 에는 NULL (사용자 사양)."""
        user = _make_user("USER_a", notification_muted=True)
        user_repo_mock.find_by_id.return_value = user

        await service.set_global_mute(user_id="USER_a", muted=False)

        assert user.notification_muted is None
        user_repo_mock.update.assert_awaited_once_with(user)


    async def test_nonexistent_user_raises(self, service, user_repo_mock):
        user_repo_mock.find_by_id.return_value = None

        with pytest.raises(ValueError, match="존재하지 않는"):
            await service.set_global_mute(user_id="USER_x", muted=True)

        user_repo_mock.update.assert_not_awaited()


# ──────────────────────────────────────────────────────────────────
# set_room_mute — 방별 차단 토글 (활성 멤버 검증 포함)
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSetRoomMute:
    async def test_muted_true_writes_true_and_calls_update(
        self, service, chat_member_repo_mock,
    ):
        member = _make_member("CR_1", "USER_a", is_left=False, notification_muted=None)
        chat_member_repo_mock.find.return_value = member

        await service.set_room_mute(
            user_id="USER_a", chat_room_id="CR_1", muted=True,
        )

        assert member.notification_muted is True
        chat_member_repo_mock.update.assert_awaited_once_with(member)


    async def test_muted_false_normalizes_to_none(
        self, service, chat_member_repo_mock,
    ):
        member = _make_member("CR_1", "USER_a", is_left=False, notification_muted=True)
        chat_member_repo_mock.find.return_value = member

        await service.set_room_mute(
            user_id="USER_a", chat_room_id="CR_1", muted=False,
        )

        assert member.notification_muted is None


    async def test_nonmember_raises(self, service, chat_member_repo_mock):
        chat_member_repo_mock.find.return_value = None

        with pytest.raises(ValueError, match="활성 멤버"):
            await service.set_room_mute(
                user_id="USER_a", chat_room_id="CR_1", muted=True,
            )

        chat_member_repo_mock.update.assert_not_awaited()


    async def test_left_member_raises(self, service, chat_member_repo_mock):
        """탈퇴자는 자기 방의 mute 설정 변경 불가 — 활성 멤버만 토글 권한."""
        member = _make_member("CR_1", "USER_a", is_left=True)
        chat_member_repo_mock.find.return_value = member

        with pytest.raises(ValueError, match="활성 멤버"):
            await service.set_room_mute(
                user_id="USER_a", chat_room_id="CR_1", muted=True,
            )

        chat_member_repo_mock.update.assert_not_awaited()
