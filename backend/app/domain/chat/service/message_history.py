"""방 리스트 / 메시지 히스토리 조회 (REST 읽기 전용).

`next_cursor = messages[-1].server_seq` — 정렬 방향과 무관하게 클라가 그대로 다음 호출에 전달.
"""
from typing import Optional

from app.domain.friend.repository.friendship import FriendshipRepository
from app.domain.chat.service.exception import ChatRoomNotFoundError
from app.domain.chat.repository.chat_room import ChatRoomRepository
from app.domain.chat.repository.chat_message import ChatMessageRepository
from app.domain.chat.repository.chat_member import ChatRoomMemberRepository
from app.domain.chat.model.chat_room import ChatRoom, ChatRoomType
from app.domain.chat.dto.room import (
    ChatRoomData,
    ChatRoomListData,
    ChatRoomPeerData,
    LastMessagePreviewData,
    RoomMemberData,
    RoomMemberListData,
)
from app.domain.chat.dto.message import ChatMessageData, MessageListData
from app.domain.auth.repository.user import UserRepository
from app.domain.auth.model.user import User
from app.database.session import UnitOfWork, mongodb, transactional
from app.core.redis import get_redis_client
from app.core.logger import get_logger
from app.core.chat.redis_key import unread_key


logger = get_logger("chat.history")


class MessageHistoryService:
    """읽기 전용 — 방 리스트 / 메시지 히스토리 페이징."""

    def __init__(self, uow: UnitOfWork):
        self.uow = uow


    @transactional
    async def list_rooms(self, me_id: str) -> ChatRoomListData:
        """내가 속한 활성 방을 effective_last_at DESC 로 PAGE_SIZE 까지."""
        chat_room_repo = ChatRoomRepository(self._session)
        user_repo = UserRepository(self._session)
        message_repo = ChatMessageRepository(mongodb.database)
        redis_hot = await get_redis_client()

        rows = await chat_room_repo.find_rooms_of_user(me_id)

        peer_ids = [pid for _, pid, _ in rows if pid is not None]
        peer_map = await user_repo.find_by_ids_with_profile(peer_ids)

        unread_raw = await redis_hot.hgetall(unread_key(me_id))
        unread_map = {k: int(v) for k, v in unread_raw.items()}

        message_ids = [r.last_message_id for r, _, _ in rows if r.last_message_id]
        messages_by_id = await message_repo.find_by_ids(message_ids)

        items = [
            self._room_to_dto(
                room=room,
                peer_user_id=peer_user_id,
                peer_user=peer_map.get(peer_user_id) if peer_user_id else None,
                unread_count=unread_map.get(room.chat_room_id, 0),
                last_message_doc=(
                    messages_by_id.get(room.last_message_id) if room.last_message_id else None
                ),
                notification_muted=mute is True,
            )
            for room, peer_user_id, mute in rows
        ]

        return ChatRoomListData(items=items, next_cursor=None)


    @transactional
    async def get_room(self, *, me_id: str, room_id: str) -> ChatRoomData:
        """방 1건 상세. 권한: 방 존재 → 404, 활성 멤버 → 403 (탈퇴자는 방을 못 봄)."""
        chat_room_repo = ChatRoomRepository(self._session)
        member_repo = ChatRoomMemberRepository(self._session)
        user_repo = UserRepository(self._session)
        message_repo = ChatMessageRepository(mongodb.database)
        redis_hot = await get_redis_client()

        room = await chat_room_repo.find_by_id(room_id)
        if room is None:
            raise ChatRoomNotFoundError("존재하지 않는 방입니다.")

        # 권한 + mute 를 한 번에 — is_active_member 별도 호출 불필요.
        member = await member_repo.find(room_id, me_id)
        if member is None or member.is_left:
            raise PermissionError("이 방의 멤버가 아닙니다.")

        peer_user_id: Optional[str] = None
        if room.type == ChatRoomType.DIRECT:
            peer_user_id = (
                room.direct_user_b_id if room.direct_user_a_id == me_id
                else room.direct_user_a_id
            )

        peer_user = (
            await user_repo.find_by_id_with_profile(peer_user_id)
            if peer_user_id else None
        )

        unread_raw = await redis_hot.hget(unread_key(me_id), room_id)
        unread_count = int(unread_raw) if unread_raw is not None else 0

        last_message_doc: Optional[dict] = None
        if room.last_message_id:
            last_message_doc = await message_repo.find_by_id(room.last_message_id)

        return self._room_to_dto(
            room=room,
            peer_user_id=peer_user_id,
            peer_user=peer_user,
            unread_count=unread_count,
            last_message_doc=last_message_doc,
            notification_muted=member.notification_muted is True,
        )


    @transactional
    async def list_room_members(
        self, *, me_id: str, room_id: str,
    ) -> RoomMemberListData:
        """그룹 방 활성 참여자 (joined_at ASC). 활성 멤버만 조회 가능, direct 방은 400."""
        chat_room_repo = ChatRoomRepository(self._session)
        member_repo = ChatRoomMemberRepository(self._session)

        room = await chat_room_repo.find_by_id(room_id)
        if room is None:
            raise ChatRoomNotFoundError("존재하지 않는 방입니다.")
        if not await member_repo.is_active_member(room_id, me_id):
            raise PermissionError("이 방의 멤버가 아닙니다.")
        if room.type != ChatRoomType.GROUP:
            raise ValueError("그룹 방의 참여자 목록만 조회할 수 있습니다.")

        users = await member_repo.find_active_member_users(room_id)
        return RoomMemberListData(items=[self._user_to_member_dto(u) for u in users])


    @transactional
    async def list_invitable_friends(
        self, *, me_id: str, room_id: str,
    ) -> RoomMemberListData:
        """방에 안 들어온 내 친구 목록 — 그룹 방 초대 UI 용. 재초대 가능한 탈퇴자 포함."""
        chat_room_repo = ChatRoomRepository(self._session)
        member_repo = ChatRoomMemberRepository(self._session)
        friendship_repo = FriendshipRepository(self._session)
        user_repo = UserRepository(self._session)

        room = await chat_room_repo.find_by_id(room_id)
        if room is None:
            raise ChatRoomNotFoundError("존재하지 않는 방입니다.")
        if not await member_repo.is_active_member(room_id, me_id):
            raise PermissionError("이 방의 멤버가 아닙니다.")
        if room.type != ChatRoomType.GROUP:
            raise ValueError("그룹 방에만 친구를 초대할 수 있습니다.")

        friend_ids = await friendship_repo.find_accepted_friend_ids(me_id)
        if not friend_ids:
            return RoomMemberListData(items=[])

        active_ids = set(await member_repo.find_active_member_ids(room_id))
        invitable_ids = friend_ids - active_ids
        if not invitable_ids:
            return RoomMemberListData(items=[])

        users_map = await user_repo.find_by_ids_with_profile(sorted(invitable_ids))
        items = [
            self._user_to_member_dto(users_map[uid])
            for uid in sorted(invitable_ids)
            if uid in users_map
        ]
        return RoomMemberListData(items=items)


    @transactional
    async def find_messages_before(
        self,
        *,
        me_id: str,
        room_id: str,
        before_server_seq: int,
        limit: int,
    ) -> MessageListData:
        """`server_seq < before` 인 메시지 DESC limit 건 + has_more."""
        await self._assert_room_member(room_id, me_id)

        message_repo = ChatMessageRepository(mongodb.database)
        raw = await message_repo.find_before(room_id, before_server_seq, limit)
        return self._to_message_list_dto(raw, limit=limit)


    @transactional
    async def find_messages_after(
        self,
        *,
        me_id: str,
        room_id: str,
        after_server_seq: int,
        limit: int,
    ) -> MessageListData:
        """`server_seq > after` 인 메시지 ASC limit 건 + has_more."""
        await self._assert_room_member(room_id, me_id)

        message_repo = ChatMessageRepository(mongodb.database)
        raw = await message_repo.find_after(room_id, after_server_seq, limit)
        return self._to_message_list_dto(raw, limit=limit)


    async def get_unread_counts(self, me_id: str) -> dict[str, int]:
        """Redis `unread:{user_id}` HASH 를 dict 로 반환. WS 연결 직후 동기화 송신용."""
        redis_hot = await get_redis_client()
        raw = await redis_hot.hgetall(unread_key(me_id))
        return {k: int(v) for k, v in raw.items()}


    async def _assert_room_member(self, room_id: str, user_id: str) -> None:
        member_repo = ChatRoomMemberRepository(self._session)
        if not await member_repo.is_active_member(room_id, user_id):
            raise PermissionError("이 방의 멤버가 아닙니다.")


    @staticmethod
    def _user_to_member_dto(user: User) -> RoomMemberData:
        """detail 결손 시 닉네임 빈 문자열 fallback — join 누락 방어."""
        detail = user.detail
        return RoomMemberData(
            user_id=user.user_id,
            user_name=detail.user_name if detail else "",
            profile_image_url=detail.profile_image_url if detail else None,
        )


    @staticmethod
    def _room_to_dto(
        *,
        room: ChatRoom,
        peer_user_id: Optional[str],
        peer_user,
        unread_count: int,
        last_message_doc: Optional[dict],
        notification_muted: bool,
    ) -> ChatRoomData:
        """방 1건 → DTO. 탈퇴한 peer 는 필드 모두 None."""
        peer_dto: Optional[ChatRoomPeerData] = None
        if peer_user_id is not None:
            if peer_user is None:
                # 탈퇴자의 SET NULL 로 보통 peer_user_id 가 이미 None 이라 여기 진입 안 함 — 방어.
                peer_dto = ChatRoomPeerData(
                    user_id=peer_user_id, user_name=None, profile_image_url=None,
                )
            else:
                detail = peer_user.detail
                peer_dto = ChatRoomPeerData(
                    user_id=peer_user.user_id,
                    user_name=detail.user_name if detail else None,
                    profile_image_url=detail.profile_image_url if detail else None,
                )
        elif room.type.value == "direct":
            peer_dto = ChatRoomPeerData(
                user_id=None, user_name=None, profile_image_url=None,
            )

        last_message_dto: Optional[LastMessagePreviewData] = None
        if last_message_doc is not None:
            last_message_dto = LastMessagePreviewData(
                message_id=last_message_doc["_id"],
                server_seq=int(last_message_doc["server_seq"]),
                sender_id=last_message_doc.get("sender_id"),
                type=last_message_doc.get("type", "text"),
                content=last_message_doc.get("content") if last_message_doc.get("deleted_at") is None else None,
                created_at=last_message_doc["created_at"],
            )

        return ChatRoomData(
            chat_room_id=room.chat_room_id,
            type=room.type,
            title=room.title,
            peer=peer_dto,
            last_message=last_message_dto,
            unread_count=unread_count,
            last_message_at=room.last_message_at,
            effective_last_at=room.effective_last_at or room.created_at,
            notification_muted=notification_muted,
        )


    @staticmethod
    def _to_message_list_dto(raw: list[dict], *, limit: int) -> MessageListData:
        """repo 가 `limit+1` 로 조회 → 넘치면 has_more=True."""
        has_more = len(raw) > limit
        items_raw = raw[:limit]
        items = [
            ChatMessageData(
                message_id=doc["_id"],
                chat_room_id=doc["chat_room_id"],
                server_seq=int(doc["server_seq"]),
                sender_id=doc.get("sender_id"),
                type=doc.get("type", "text"),
                content=doc.get("content") if doc.get("deleted_at") is None else None,
                created_at=doc["created_at"],
                edited_at=doc.get("edited_at"),
                deleted_at=doc.get("deleted_at"),
            )
            for doc in items_raw
        ]
        next_cursor = items[-1].server_seq if items and has_more else None
        return MessageListData(messages=items, has_more=has_more, next_cursor=next_cursor)
