"""MuteService 통합 — 서비스 → repository → 실 DB row 까지 검증.

핵심:
    - 저장 정규화 (True 만 row 에 적고, False 는 NULL 로 되돌림)
    - 활성 멤버만 방별 토글 가능 (비멤버 / 탈퇴자 거절)
    - 존재하지 않는 유저 거절
"""
from test.integration.domain.notification.conftest import (
    fetch_member,
    fetch_user,
)
import pytest


pytestmark = pytest.mark.integration


# ──────────────────── 전역 mute ────────────────────

class TestSetGlobalMuteFlow:
    async def test_true_persists_as_true(
        self, mute_service, session_factory, seed_users,
    ):
        [user_id] = await seed_users(1)

        await mute_service.set_global_mute(user_id=user_id, muted=True)

        row = await fetch_user(session_factory, user_id)
        assert row.notification_muted is True


    async def test_false_normalizes_to_null(
        self, mute_service, session_factory, seed_users,
    ):
        """저장 정규화: False 입력은 DB 에 NULL 로 — 가드(`is True`) 와 일관."""
        [user_id] = await seed_users(1)

        await mute_service.set_global_mute(user_id=user_id, muted=True)
        await mute_service.set_global_mute(user_id=user_id, muted=False)

        row = await fetch_user(session_factory, user_id)
        assert row.notification_muted is None


    async def test_idempotent_double_mute(
        self, mute_service, session_factory, seed_users,
    ):
        """이미 차단된 상태에서 다시 mute=True 호출해도 정상."""
        [user_id] = await seed_users(1)

        await mute_service.set_global_mute(user_id=user_id, muted=True)
        await mute_service.set_global_mute(user_id=user_id, muted=True)

        row = await fetch_user(session_factory, user_id)
        assert row.notification_muted is True


    async def test_nonexistent_user_raises(self, mute_service):
        with pytest.raises(ValueError, match="존재하지 않는"):
            await mute_service.set_global_mute(user_id="USER_NONE", muted=True)


# ──────────────────── 방별 mute ────────────────────

class TestSetRoomMuteFlow:
    async def test_true_persists_only_for_caller(
        self, mute_service, session_factory, seed_room_with_members,
    ):
        """본인 row 만 True — 같은 방의 다른 멤버는 영향 없음."""
        room_id, [me, other] = await seed_room_with_members(2)

        await mute_service.set_room_mute(
            user_id=me, chat_room_id=room_id, muted=True,
        )

        my_row = await fetch_member(session_factory, room_id, me)
        other_row = await fetch_member(session_factory, room_id, other)
        assert my_row.notification_muted is True
        assert other_row.notification_muted is None  # 다른 멤버 미영향


    async def test_false_normalizes_to_null(
        self, mute_service, session_factory, seed_room_with_members,
    ):
        room_id, [me, _] = await seed_room_with_members(2)

        await mute_service.set_room_mute(
            user_id=me, chat_room_id=room_id, muted=True,
        )
        await mute_service.set_room_mute(
            user_id=me, chat_room_id=room_id, muted=False,
        )

        row = await fetch_member(session_factory, room_id, me)
        assert row.notification_muted is None


    async def test_non_member_raises(
        self, mute_service, seed_room_with_members, seed_users,
    ):
        room_id, _ = await seed_room_with_members(2)
        [outsider] = await seed_users(1)  # 방 멤버 아님

        with pytest.raises(ValueError, match="활성 멤버"):
            await mute_service.set_room_mute(
                user_id=outsider, chat_room_id=room_id, muted=True,
            )


    async def test_left_member_raises(
        self, mute_service, session_factory, seed_room_with_members,
    ):
        """탈퇴자(`is_left=True`) 는 자기 방 mute 토글 불가."""
        room_id, [me, _] = await seed_room_with_members(2)

        # is_left=True 로 직접 변경
        async with session_factory() as session:
            from app.domain.chat.model.chat_room_member import ChatRoomMember
            member = await session.get(ChatRoomMember, (room_id, me))
            member.is_left = True
            await session.commit()

        with pytest.raises(ValueError, match="활성 멤버"):
            await mute_service.set_room_mute(
                user_id=me, chat_room_id=room_id, muted=True,
            )
