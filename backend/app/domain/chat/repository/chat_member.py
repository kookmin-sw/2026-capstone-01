from typing import Optional
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, update

from app.domain.chat.model.chat_room_member import ChatRoomMember
from app.domain.auth.model.user import User


class ChatRoomMemberRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    # ──────────────────── Create ────────────────────

    async def save(self, member: ChatRoomMember) -> ChatRoomMember:
        self.session.add(member)
        await self.session.flush()
        return member


    async def save_all(self, members: list[ChatRoomMember]) -> list[ChatRoomMember]:
        """방 생성 직후 creator + 초대 멤버 일괄 등록."""
        self.session.add_all(members)
        await self.session.flush()
        return members


    # ──────────────────── Read (단건) ────────────────────

    async def find(
        self,
        chat_room_id: str,
        user_id: str,
    ) -> Optional[ChatRoomMember]:
        """복합 PK 단건 조회 (is_left 여부 무관)."""
        return await self.session.get(ChatRoomMember, (chat_room_id, user_id))


    # ──────────────────── Read (목록) ────────────────────

    async def find_active_member_users(self, chat_room_id: str) -> list[User]:
        """방의 활성 멤버 User + detail 을 joined_at ASC 로 (참여자 목록 노출용)."""
        stmt = (
            select(User)
            .options(joinedload(User.detail))
            .join(ChatRoomMember, ChatRoomMember.user_id == User.user_id)
            .where(
                ChatRoomMember.chat_room_id == chat_room_id,
                ChatRoomMember.is_left.is_(False),
            )
            .order_by(ChatRoomMember.joined_at.asc(), User.user_id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())


    async def find_active_member_ids(self, chat_room_id: str) -> list[str]:
        """방의 활성 멤버 user_id 목록 — `room:members:{R}` 캐시 miss 시 일괄 로드용."""
        stmt = select(ChatRoomMember.user_id).where(
            ChatRoomMember.chat_room_id == chat_room_id,
            ChatRoomMember.is_left.is_(False),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    async def is_active_member(self, chat_room_id: str, user_id: str) -> bool:
        """활성 멤버 여부 (is_left=false). 권한 체크용."""
        stmt = select(ChatRoomMember.user_id).where(
            ChatRoomMember.chat_room_id == chat_room_id,
            ChatRoomMember.user_id == user_id,
            ChatRoomMember.is_left.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None


    async def find_pushable_user_ids_in_room(
        self, chat_room_id: str, user_ids: list[str],
    ) -> set[str]:
        """방에서 푸시 받을 수 있는 id 집합 — 활성 멤버 + 방 알림 미차단."""
        if not user_ids:
            return set()
        stmt = select(ChatRoomMember.user_id).where(
            ChatRoomMember.chat_room_id == chat_room_id,
            ChatRoomMember.user_id.in_(user_ids),
            ChatRoomMember.is_left.is_(False),
            ChatRoomMember.notification_muted.is_not(True),
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())


    async def find_user_room_ids(self, user_id: str) -> list[str]:
        """유저가 속한 활성 방 ID. WS 연결 시 초기 구독용."""
        stmt = select(ChatRoomMember.chat_room_id).where(
            ChatRoomMember.user_id == user_id,
            ChatRoomMember.is_left.is_(False),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    async def find_last_read_seqs(
        self,
        user_id: str,
        room_ids: Optional[list[str]] = None,
    ) -> dict[str, int]:
        """유저의 방별 `last_read_message_server_seq` 배치 조회 — unread 복구 전용.

        NULL 은 0 으로 정규화 → "전체 메시지" 가 미읽음 카운트 대상이 됨.
        `room_ids=None` 이면 활성 방 전체.
        """
        conditions = [
            ChatRoomMember.user_id == user_id,
            ChatRoomMember.is_left.is_(False),
        ]
        if room_ids is not None:
            if not room_ids:
                return {}
            conditions.append(ChatRoomMember.chat_room_id.in_(room_ids))

        stmt = select(
            ChatRoomMember.chat_room_id,
            ChatRoomMember.last_read_message_server_seq,
        ).where(*conditions)
        result = await self.session.execute(stmt)
        return {row[0]: int(row[1] or 0) for row in result.all()}


    # ──────────────────── Update ────────────────────

    async def update(self, member: ChatRoomMember) -> ChatRoomMember:
        await self.session.flush()
        return member


    async def mark_read(
        self, chat_room_id: str, user_id: str, new_seq: int,
    ) -> Optional[int]:
        """`last_read_message_server_seq = GREATEST(COALESCE(기존, 0), new_seq)`.

        활성 멤버 row 에만 반영 — 탈퇴자는 None 반환.
        RETURNING 으로 최종 seq 를 돌려받아 ACK 에 사용.
        다중 세션에서 다른 seq 로 동시 read 가 와도 GREATEST 가 regress 차단.
        """
        stmt = (
            update(ChatRoomMember)
            .where(
                ChatRoomMember.chat_room_id == chat_room_id,
                ChatRoomMember.user_id == user_id,
                ChatRoomMember.is_left.is_(False),
            )
            .values(
                last_read_message_server_seq=func.greatest(
                    func.coalesce(ChatRoomMember.last_read_message_server_seq, 0),
                    new_seq,
                ),
                last_read_at=func.now(),
            )
            .returning(ChatRoomMember.last_read_message_server_seq)
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


    async def count_readers_up_to(
        self,
        chat_room_id: str,
        server_seq: int,
        exclude_user_id: str,
    ) -> int:
        """`server_seq` 이상 읽은 활성 멤버 수 (발신자 제외).

        카톡 뱃지 = "활성 멤버 수 - (이 카운트 + 1)". 권위있는 unread 값이 필요할 때 사용.
        """
        stmt = select(func.count()).select_from(ChatRoomMember).where(
            ChatRoomMember.chat_room_id == chat_room_id,
            ChatRoomMember.is_left.is_(False),
            ChatRoomMember.user_id != exclude_user_id,
            ChatRoomMember.last_read_message_server_seq >= server_seq,
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())
