"""알림 차단(mute) — 전역(유저) / 방별(멤버) 두 레벨.

저장 정규화: True 만 row 에 적고, 해제는 NULL 로 되돌린다. 조회·가드도 `is True` 로 일관.
"""
from app.domain.chat.repository.chat_member import ChatRoomMemberRepository
from app.domain.auth.repository.user import UserRepository
from app.database.session import UnitOfWork, transactional


class MuteService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow


    @transactional
    async def set_global_mute(self, *, user_id: str, muted: bool) -> None:
        """전역 알림 차단 토글. False 면 NULL 로 해제."""
        user_repo = UserRepository(self._session)
        user = await user_repo.find_by_id(user_id)
        if user is None:
            raise ValueError("존재하지 않는 유저입니다.")
        user.notification_muted = True if muted else None
        await user_repo.update(user)


    @transactional
    async def set_room_mute(
        self, *, user_id: str, chat_room_id: str, muted: bool,
    ) -> None:
        """방별 알림 차단 토글. 활성 멤버여야 가능."""
        member_repo = ChatRoomMemberRepository(self._session)
        member = await member_repo.find(chat_room_id, user_id)
        if member is None or member.is_left:
            raise ValueError("이 방의 활성 멤버가 아닙니다.")
        member.notification_muted = True if muted else None
        await member_repo.update(member)
