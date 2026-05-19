"""방 리스트 / 메시지 히스토리 조회 서비스.

REST 로 제공되는 읽기 경로 3개:
    GET /chat/rooms                                  — 방 리스트
    GET /chat/rooms/{id}/messages?before_server_seq= — 위로 스크롤
    GET /chat/rooms/{id}/messages?after_server_seq=  — catch-up

공통 규약:
    `next_cursor = messages[-1].server_seq`  (정렬 방향 무관, 클라는 그대로 다음 호출에 전달)
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
    """읽기 전용 서비스 — 방 리스트 / 메시지 히스토리 페이징.

    모든 메서드가 `@transactional` — RDB 읽기에 세션 필요. Mongo/Redis 는 트랜잭션 외부.
    """

    def __init__(self, uow: UnitOfWork):
        self.uow = uow


    # ──────────────────── 방 리스트 ────────────────────

    @transactional
    async def list_rooms(self, me_id: str) -> ChatRoomListData:
        """ 내가 속한 활성 방을 effective_last_at DESC 로 LIMIT PAGE_SIZE (500).

        1. RDB: chat_room + chat_room_member JOIN + peer_user_id 파생
        2. RDB: 1:1 방의 peer 프로필 배치 조회 (`find_by_ids_with_profile` 1 쿼리)
        3. Redis: HGETALL unread:{me}
        4. Mongo: last_message_id 배치 조회 (미리보기)
        """
        chat_room_repo = ChatRoomRepository(self._session)
        user_repo = UserRepository(self._session)
        message_repo = ChatMessageRepository(mongodb.database)
        redis_hot = await get_redis_client()

        # 1. 방 + peer_user_id 파생
        rows = await chat_room_repo.find_rooms_of_user(me_id)

        # 2. peer 프로필 배치 조회 — 탈퇴한 유저(=결과에 없음)는 호출측 .get 으로 None fallback
        peer_ids = [pid for _, pid, _ in rows if pid is not None]
        peer_map = await user_repo.find_by_ids_with_profile(peer_ids)

        # 3. unread
        unread_raw = await redis_hot.hgetall(unread_key(me_id))
        unread_map = {k: int(v) for k, v in unread_raw.items()}

        # 4. last_message 본문 배치
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


    # ──────────────────── 단건 방 조회 ────────────────────

    @transactional
    async def get_room(self, *, me_id: str, room_id: str) -> ChatRoomData:
        """방 1건 상세 조회 — `room_joined` 이벤트 수신 후 메타 fetch 등에 사용.

        list_rooms 와 동일한 응답 스키마를 단건으로 반환한다 (peer / unread / last_message
        모두 채움). 권한 체크 우선순위:
            1. 방 존재 여부 → 404
            2. 활성 멤버 여부 → 403  (탈퇴자는 방을 못 봄)
        """
        chat_room_repo = ChatRoomRepository(self._session)
        member_repo = ChatRoomMemberRepository(self._session)
        user_repo = UserRepository(self._session)
        message_repo = ChatMessageRepository(mongodb.database)
        redis_hot = await get_redis_client()

        room = await chat_room_repo.find_by_id(room_id)
        if room is None:
            raise ChatRoomNotFoundError("존재하지 않는 방입니다.")

        # 권한 체크 + mute 상태를 한 번의 조회로 — is_active_member 별도 호출 불필요.
        member = await member_repo.find(room_id, me_id)
        if member is None or member.is_left:
            raise PermissionError("이 방의 멤버가 아닙니다.")

        # peer_user_id 파생 — 1:1 방의 상대방 (그룹은 None)
        peer_user_id: Optional[str] = None
        if room.type == ChatRoomType.DIRECT:
            if room.direct_user_a_id == me_id:
                peer_user_id = room.direct_user_b_id
            else:
                peer_user_id = room.direct_user_a_id

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


    # ──────────────────── 그룹 방 참여자 목록 ────────────────────

    @transactional
    async def list_room_members(
        self, *, me_id: str, room_id: str,
    ) -> RoomMemberListData:
        """그룹 방의 활성 참여자 목록 (joined_at 오름차순).

        권한: 활성 멤버만 조회 가능. direct 방은 `peer` 필드로 충분하므로 거절.
            1. 방 존재 → 404
            2. 활성 멤버 여부 → 403
            3. group 타입만 허용 → 400
        """
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


    # ──────────────────── 그룹 방 초대 가능 친구 목록 ────────────────────

    @transactional
    async def list_invitable_friends(
        self, *, me_id: str, room_id: str,
    ) -> RoomMemberListData:
        """방에 아직 들어오지 않은 내 친구 목록 — 그룹 방 초대 UI 용.

        권한 체크는 참여자 목록과 동일 (활성 멤버 + group 타입). 친구 ID 전체에서
        활성 멤버 ID 를 차집합 — 재초대 가능한 탈퇴자(`is_left=true`) 도 후보에 포함된다.
        """
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


    # ──────────────────── 히스토리 페이징 ────────────────────

    @transactional
    async def find_messages_before(
        self,
        *,
        me_id: str,
        room_id: str,
        before_server_seq: int,
        limit: int,
    ) -> MessageListData:
        """`server_seq < before` 인 메시지를 DESC 로 limit 건 + has_more 판정."""
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
        """`server_seq > after` 인 메시지를 ASC 로 limit 건 + has_more 판정."""
        await self._assert_room_member(room_id, me_id)

        message_repo = ChatMessageRepository(mongodb.database)
        raw = await message_repo.find_after(room_id, after_server_seq, limit)
        return self._to_message_list_dto(raw, limit=limit)


    # ──────────────────── Unread 카운트 스냅샷 ────────────────────

    async def get_unread_counts(self, me_id: str) -> dict[str, int]:
        """Redis `unread:{user_id}` HASH 를 그대로 dict 로 반환.

        WS 연결 직후 `unread_synced` 이벤트 송신용. Redis 가 비어 있으면 빈 dict 를
        돌려주는데, Phase 3 에서 이 자리에 `recover_unread_for_user` 백그라운드 복구를
        연결할 예정.

        @transactional 미적용: RDB 터치 없음.
        """
        redis_hot = await get_redis_client()
        raw = await redis_hot.hgetall(unread_key(me_id))
        return {k: int(v) for k, v in raw.items()}


    # ──────────────────── 내부 유틸 ────────────────────

    async def _assert_room_member(self, room_id: str, user_id: str) -> None:
        """권한 체크 — 방의 활성 멤버가 아니면 PermissionError."""
        member_repo = ChatRoomMemberRepository(self._session)
        if not await member_repo.is_active_member(room_id, user_id):
            raise PermissionError("이 방의 멤버가 아닙니다.")


    @staticmethod
    def _user_to_member_dto(user: User) -> RoomMemberData:
        """User + detail → RoomMemberData. detail 없는 케이스는 닉네임을 빈 문자열 fallback.

        활성 멤버는 정상 가입자만 들어오므로 detail 결손은 사실상 발생 안 하지만
        join 결과 누락 방어용으로 한 단계 안전 장치를 둔다.
        """
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
        """방 1건을 DTO 로 변환. 탈퇴한 peer 는 user_id/user_name 모두 None."""
        peer_dto: Optional[ChatRoomPeerData] = None
        if peer_user_id is not None:
            if peer_user is None:
                # 탈퇴한 사용자 — user_id 는 아직 있지만 User row 자체가 사라진 경우는
                # SET NULL 로 이미 peer_user_id=None 이 되므로 여기 진입하지 않지만, 방어.
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
            # 1:1 방인데 peer 가 탈퇴로 NULL 된 상태
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
        """`find_before`/`find_after` 가 `limit+1` 로 조회했으므로 넘치면 has_more=True."""
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
