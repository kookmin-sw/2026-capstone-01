"""채팅방 생성 / 멤버십 관리 서비스.

Phase 1: 1:1 방 생성 — idempotent, canonical 정렬, 차단 체크
Phase 2: 그룹 방 생성 / 초대 / 퇴장 / 강퇴 — 친구 정책, 재초대 시 last_read 유지,
         Redis SREM → RDB UPDATE 순서 (C3)
"""
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone

from app.domain.friend.repository.user_block import UserBlockRepository
from app.domain.friend.repository.friendship import FriendshipRepository
from app.domain.chat.service.exception import ChatRoomNotFoundError
from app.domain.chat.repository.chat_room import ChatRoomRepository
from app.domain.chat.repository.chat_message import ChatMessageRepository
from app.domain.chat.repository.chat_member import ChatRoomMemberRepository
from app.domain.chat.model.chat_room_member import ChatRoomMember
from app.domain.chat.model.chat_room import ChatRoom, ChatRoomType
from app.domain.chat.dto.room import ChatRoomData, ChatRoomPeerData
from app.domain.auth.repository.user import UserRepository
from app.database.session import UnitOfWork, mongodb, transactional
from app.core.redis import get_redis_client
from app.core.logger import get_logger
from app.core.chat.redis_key import (
    room_members_key,
    room_seq_key,
    unread_key,
    ROOM_MEMBERS_TTL,
)


logger = get_logger("chat.room")


class RoomService:
    """채팅방 생명주기 — 생성·멤버 등록·구독 이벤트 발행."""

    def __init__(self, uow: UnitOfWork, fanout_service, message_service):
        # fanout_service / message_service 는 type hint 생략 (순환 import 회피)
        self.uow = uow
        self._fanout = fanout_service
        self._message_service = message_service


    # ──────────────────── 1:1 방 생성 ────────────────────

    @transactional
    async def create_direct_room(self, me_id: str, peer_user_id: str) -> ChatRoomData:
        """1:1 방 idempotent 생성.

        순서:
        1. 자기 자신과의 방 금지
        2. 상대 유저 존재 검증
        3. 차단 관계 검증 (양방향 한 번에 — 상호 차단이어도 내 차단을 우선 안내)
        4. canonical 정렬된 (a, b) 로 기존 방 조회
        5. 없으면 SAVEPOINT 로 INSERT — UNIQUE race 는 IntegrityError 재조회로 복구
        6. Redis `room:members:{R}` 캐시 + 양쪽 유저에 `room_joined` 이벤트 발행
        """
        if me_id == peer_user_id:
            raise ValueError("자기 자신과의 방은 만들 수 없습니다.")

        chat_room_repo = ChatRoomRepository(self._session)
        member_repo = ChatRoomMemberRepository(self._session)
        block_repo = UserBlockRepository(self._session)
        user_repo = UserRepository(self._session)

        # 상대 유저 존재 (탈퇴자 선점 UX 를 위해 detail 조인 사용)
        peer = await user_repo.find_by_id_with_profile(peer_user_id)
        if peer is None:
            raise ValueError("존재하지 않는 유저입니다.")

        # 차단 관계 검증 (양방향)
        blocks = await block_repo.find_blocks_between(me_id, peer_user_id)
        if any(b.blocker_id == me_id for b in blocks):
            raise ValueError("차단한 유저와는 방을 만들 수 없습니다. 먼저 차단을 해제해주세요.")
        if blocks:
            raise ValueError("해당 유저와는 방을 만들 수 없습니다.")

        # canonical 정렬
        user_a, user_b = sorted([me_id, peer_user_id])

        # 기존 방 재활용 (idempotent)
        existing = await chat_room_repo.find_direct_by_pair(user_a, user_b)
        if existing is not None:
            return await self._to_dto(existing, me_id=me_id, peer=peer)

        # 새 방 생성 — UNIQUE race 시 SAVEPOINT rollback + 재조회
        new_room = ChatRoom(
            type=ChatRoomType.DIRECT,
            creator_id=me_id,
            direct_user_a_id=user_a,
            direct_user_b_id=user_b,
        )
        try:
            async with self._session.begin_nested():
                await chat_room_repo.save(new_room)
                await member_repo.save_all([
                    ChatRoomMember(chat_room_id=new_room.chat_room_id, user_id=user_a),
                    ChatRoomMember(chat_room_id=new_room.chat_room_id, user_id=user_b),
                ])
        except IntegrityError:
            existing = await chat_room_repo.find_direct_by_pair(user_a, user_b)
            if existing is None:
                raise ValueError("방 생성 경합 실패. 잠시 후 다시 시도해주세요.")
            return await self._to_dto(existing, me_id=me_id, peer=peer)

        # Redis 멤버 캐시 + 양쪽 유저에 room_joined 이벤트
        room_id = new_room.chat_room_id
        redis = await get_redis_client()
        pipe = redis.pipeline(transaction=True)
        pipe.sadd(room_members_key(room_id), user_a, user_b)
        pipe.expire(room_members_key(room_id), ROOM_MEMBERS_TTL)
        await pipe.execute()

        # 구독을 fan-out 보다 먼저 — fan_out_to_user 의 await 사이 event loop 가
        # 양보해 한쪽 유저가 room_joined 직후 send_message 를 던질 경우, 아직 _room_subs
        # 에 안 들어간 상대방이 첫 메시지를 누락하는 race 를 차단.
        # node_channel 모드에서도 동일 publisher 가 같은 채널로 publish 하므로 순서 보존.
        for uid in (user_a, user_b):
            await self._fanout.subscribe_user_to_room(uid, room_id)

        # 본인 포함 양쪽에 발행 — 같은 유저의 다른 세션 (폰→PC) 도 자동 구독되도록 (C3)
        for uid in (user_a, user_b):
            await self._fanout.fan_out_to_user(
                uid,
                {"type": "room_joined", "room_id": room_id},
            )

        logger.info("1:1 방 생성 완료: room_id={}, a={}, b={}", room_id, user_a, user_b)
        return await self._to_dto(new_room, me_id=me_id, peer=peer)


    # ──────────────────── WS 연결 시 초기 방 구독용 ────────────────────

    @transactional
    async def list_user_room_ids(self, user_id: str) -> list[str]:
        """유저가 속한 활성 방 ID 목록. WS 연결 직후 `register_ws_to_room` 호출에 사용."""
        member_repo = ChatRoomMemberRepository(self._session)
        return await member_repo.find_user_room_ids(user_id)


    # ──────────────────── 그룹 방 생성 ────────────────────

    @transactional
    async def create_group_room(
        self,
        me_id: str,
        title: str,
        member_ids: list[str],
    ) -> ChatRoomData:
        """그룹 방 생성. creator 포함 `len(member_ids) + 1` 명 초기 멤버.

        member_ids 중 본인과 중복은 제거. 친구가 아닌 user_id 가 하나라도 있으면
        **전체 실패** — 부분 성공은 운영자 혼란만 키우므로 명시적 거절.
        `block` 발생 시 friendship 이 자동 삭제되므로 "친구 체크" 한 번으로 차단
        관계도 자연히 걸러진다.
        """
        targets = {uid for uid in member_ids if uid != me_id}
        if not targets:
            raise ValueError("초대할 대상이 없습니다 (본인 외 멤버 없음).")

        friendship_repo = FriendshipRepository(self._session)
        chat_room_repo = ChatRoomRepository(self._session)
        member_repo = ChatRoomMemberRepository(self._session)

        friend_ids = await friendship_repo.find_accepted_friend_ids_with(me_id, targets)
        non_friends = targets - friend_ids
        if non_friends:
            raise ValueError(
                f"친구가 아닌 유저는 초대할 수 없습니다: {sorted(non_friends)}"
            )

        all_member_ids = sorted({me_id, *targets})
        new_room = ChatRoom(
            type=ChatRoomType.GROUP,
            title=title,
            creator_id=me_id,
            direct_user_a_id=None,
            direct_user_b_id=None,
        )
        await chat_room_repo.save(new_room)
        await member_repo.save_all([
            ChatRoomMember(
                chat_room_id=new_room.chat_room_id,
                user_id=uid,
                last_read_message_server_seq=None,
            )
            for uid in all_member_ids
        ])

        room_id = new_room.chat_room_id
        redis = await get_redis_client()
        pipe = redis.pipeline(transaction=True)
        pipe.sadd(room_members_key(room_id), *all_member_ids)
        pipe.expire(room_members_key(room_id), ROOM_MEMBERS_TTL)
        for uid in all_member_ids:
            pipe.hset(unread_key(uid), room_id, 0)
        await pipe.execute()

        # 구독을 fan-out 보다 먼저 — race 차단 (room_joined await 사이 누군가 송신 시
        # 아직 미구독 멤버 누락 방지). 시스템 메시지 fan_out_to_room 도 안전하게 도달.
        for uid in all_member_ids:
            await self._fanout.subscribe_user_to_room(uid, room_id)

        for uid in all_member_ids:
            await self._fanout.fan_out_to_user(
                uid, {"type": "room_joined", "room_id": room_id},
            )

        # 타임라인 시스템 메시지 — "A 님이 방을 만들었습니다"
        await self._message_service.send_system_message(
            room_id=room_id,
            action="created",
            actor_id=me_id,
        )

        logger.info(
            "그룹 방 생성: room_id={}, creator={}, members={}",
            room_id, me_id, all_member_ids,
        )
        return self._to_group_dto(new_room)


    # ──────────────────── 멤버 초대 ────────────────────

    @transactional
    async def invite_members(
        self,
        me_id: str,
        room_id: str,
        user_ids: list[str],
    ) -> tuple[list[str], list[str]]:
        """그룹 방에 멤버 초대.

        신규 멤버: `last_read = current_seq` — 과거 메시지는 읽은 것으로 간주, unread=0.
        재초대 (기존 is_left=true): `last_read` 유지 — 탈퇴 전 읽은 시점 보존. unread 는
        `current_seq - last_read` 로 재계산 (naive, Phase 3 의 recover_unread_for_user
        로 정밀화 예정).
        재초대 시 `notification_muted` 는 NULL 로 리셋 — 새로 들어오는 시점이라 과거의
        mute 선호를 무의식적으로 끌고 가는 게 더 어색함. 다시 끄고 싶으면 사용자가
        명시적으로 토글.

        Returns:
            (invited, skipped_already_member) — 실제 초대된 / 이미 멤버라 스킵된
        """
        chat_room_repo = ChatRoomRepository(self._session)
        member_repo = ChatRoomMemberRepository(self._session)
        friendship_repo = FriendshipRepository(self._session)
        message_repo = ChatMessageRepository(mongodb.database)

        room = await chat_room_repo.find_by_id(room_id)
        if room is None:
            raise ChatRoomNotFoundError("존재하지 않는 방입니다.")
        if room.type != ChatRoomType.GROUP:
            raise ValueError("그룹 방에만 멤버를 초대할 수 있습니다.")
        if not await member_repo.is_active_member(room_id, me_id):
            raise PermissionError("이 방의 활성 멤버만 초대할 수 있습니다.")

        targets = {uid for uid in user_ids if uid != me_id}
        if not targets:
            raise ValueError("초대할 대상이 없습니다.")

        friend_ids = await friendship_repo.find_accepted_friend_ids_with(me_id, targets)
        non_friends = targets - friend_ids
        if non_friends:
            raise ValueError(
                f"친구가 아닌 유저는 초대할 수 없습니다: {sorted(non_friends)}"
            )

        current_seq = await self._get_current_seq(message_repo, room_id)

        invited: list[str] = []
        skipped: list[str] = []
        new_members: list[str] = []
        rejoined: list[tuple[str, int]] = []  # (uid, last_read)

        for uid in sorted(targets):
            existing = await member_repo.find(room_id, uid)
            if existing is not None and not existing.is_left:
                skipped.append(uid)
                continue
            if existing is not None and existing.is_left:
                existing.is_left = False
                existing.joined_at = datetime.now(timezone.utc)
                existing.notification_muted = None
                rejoined.append((uid, existing.last_read_message_server_seq or 0))
                invited.append(uid)
            else:
                await member_repo.save(ChatRoomMember(
                    chat_room_id=room_id,
                    user_id=uid,
                    last_read_message_server_seq=current_seq or None,
                ))
                new_members.append(uid)
                invited.append(uid)

        if not invited:
            return [], skipped

        redis = await get_redis_client()
        pipe = redis.pipeline(transaction=True)
        pipe.sadd(room_members_key(room_id), *invited)
        pipe.expire(room_members_key(room_id), ROOM_MEMBERS_TTL)
        for uid, last_read in rejoined:
            pipe.hset(unread_key(uid), room_id, max(0, current_seq - last_read))
        for uid in new_members:
            pipe.hset(unread_key(uid), room_id, 0)
        await pipe.execute()

        # 구독을 fan-out 보다 먼저 — race 차단 (room_joined await 사이 invitee 가 송신 시
        # 아직 미구독 다른 invitee 누락 방지)
        for uid in invited:
            await self._fanout.subscribe_user_to_room(uid, room_id)

        for uid in invited:
            await self._fanout.fan_out_to_user(
                uid, {"type": "room_joined", "room_id": room_id},
            )

        # 타임라인 시스템 메시지 — "A 님이 B, C 를 초대했습니다"
        await self._message_service.send_system_message(
            room_id=room_id,
            action="join",
            actor_id=me_id,
            target_ids=invited,
        )

        logger.info(
            "멤버 초대: room_id={}, inviter={}, invited={}, skipped={}",
            room_id, me_id, invited, skipped,
        )
        return invited, skipped


    # ──────────────────── 퇴장 ────────────────────

    @transactional
    async def leave_room(self, me_id: str, room_id: str) -> None:
        """그룹 방 퇴장 (본인). **C3 순서**: Redis SREM 먼저, RDB UPDATE 나중.

        Redis SREM 이 먼저 실행되면 퇴장자가 in-flight 로 보내던 메시지가
        `_ensure_membership` 에서 즉시 거절되어 "이미 나간 방에 메시지" 가 방지된다.
        """
        chat_room_repo = ChatRoomRepository(self._session)
        member_repo = ChatRoomMemberRepository(self._session)

        room = await chat_room_repo.find_by_id(room_id)
        if room is None:
            raise ChatRoomNotFoundError("존재하지 않는 방입니다.")
        if room.type != ChatRoomType.GROUP:
            raise ValueError("그룹 방만 퇴장할 수 있습니다.")

        member = await member_repo.find(room_id, me_id)
        if member is None or member.is_left:
            raise PermissionError("이 방의 활성 멤버가 아닙니다.")

        redis = await get_redis_client()
        pipe = redis.pipeline(transaction=True)
        pipe.srem(room_members_key(room_id), me_id)
        pipe.hdel(unread_key(me_id), room_id)
        await pipe.execute()

        member.is_left = True
        await member_repo.update(member)

        await self._fanout.fan_out_to_user(
            me_id, {"type": "room_left", "room_id": room_id},
        )

        # 시스템 메시지 fan-out 이전에 구독 해제:
        #   1) leak 차단 보장 — send_system_message 가 실패해도 이미 구독 해제됨
        #   2) UX — leaver 가 자기 "방 나감" 시스템 메시지를 받지 않음 (room_left 이벤트로
        #      이미 별도 알림). 카톡/슬랙/디스코드 표준 동작과 일관.
        await self._fanout.unsubscribe_user_from_room(me_id, room_id)

        # 타임라인 시스템 메시지 — "A 님이 방을 나갔습니다" (다른 방 멤버용)
        await self._message_service.send_system_message(
            room_id=room_id,
            action="leave",
            actor_id=me_id,
        )

        logger.info("그룹 방 퇴장: room_id={}, user_id={}", room_id, me_id)


    # ──────────────────── 강퇴 ────────────────────

    @transactional
    async def kick_member(
        self, me_id: str, room_id: str, target_user_id: str,
    ) -> None:
        """그룹 방에서 특정 멤버 강퇴. creator 전용 권한.

        creator 가 이미 방을 떠난 상태면 권한을 잃는다 (PHASE_2 P5 — 권한 승계 없음).
        자기 자신은 kick 이 아닌 leave API 를 사용해야 한다.
        """
        if me_id == target_user_id:
            raise ValueError("자기 자신은 강퇴할 수 없습니다. 퇴장 API 를 사용하세요.")

        chat_room_repo = ChatRoomRepository(self._session)
        member_repo = ChatRoomMemberRepository(self._session)

        room = await chat_room_repo.find_by_id(room_id)
        if room is None:
            raise ChatRoomNotFoundError("존재하지 않는 방입니다.")
        if room.type != ChatRoomType.GROUP:
            raise ValueError("그룹 방에서만 강퇴할 수 있습니다.")
        if room.creator_id != me_id:
            raise PermissionError("방장만 강퇴할 수 있습니다.")
        if not await member_repo.is_active_member(room_id, me_id):
            raise PermissionError("방장이 이미 방을 떠난 상태입니다.")

        target = await member_repo.find(room_id, target_user_id)
        if target is None or target.is_left:
            raise ValueError("강퇴 대상이 활성 멤버가 아닙니다.")

        redis = await get_redis_client()
        pipe = redis.pipeline(transaction=True)
        pipe.srem(room_members_key(room_id), target_user_id)
        pipe.hdel(unread_key(target_user_id), room_id)
        await pipe.execute()

        target.is_left = True
        await member_repo.update(target)

        await self._fanout.fan_out_to_user(
            target_user_id, {"type": "room_left", "room_id": room_id},
        )

        # leave_room 과 동일 — 시스템 메시지 이전에 구독 해제 (leak 차단 + 표준 UX)
        await self._fanout.unsubscribe_user_from_room(target_user_id, room_id)

        # 타임라인 시스템 메시지 — "A 님이 B 를 내보냈습니다" (다른 방 멤버용)
        await self._message_service.send_system_message(
            room_id=room_id,
            action="kick",
            actor_id=me_id,
            target_ids=[target_user_id],
        )

        logger.info(
            "멤버 강퇴: room_id={}, kicker={}, target={}",
            room_id, me_id, target_user_id,
        )


    # ──────────────────── 읽음 처리 (Phase 2 #3) ────────────────────

    @transactional
    async def mark_read(
        self,
        *,
        me_id: str,
        me_session_id: str,
        room_id: str,
        up_to_server_seq: int,
    ) -> int:
        """읽음 포인터 갱신 + unread 리셋 + fan-out.

        흐름:
        1. 방 존재 확인
        2. RDB `last_read_message_server_seq = GREATEST(기존, :seq)` — regress 방지
        3. 활성 멤버가 아니면 권한 에러 (탈퇴자의 read 요청 무효화)
        4. Redis `unread:{me} R = 0` 로 초기화
        5. 발신 세션에 `read_ack`, 방에 `read` 이벤트 발행

        Returns:
            최종 반영된 `last_read_message_server_seq` (regress 시엔 기존 값 유지됨).
        """
        if up_to_server_seq <= 0:
            raise ValueError("up_to_server_seq 는 1 이상이어야 합니다.")

        chat_room_repo = ChatRoomRepository(self._session)
        member_repo = ChatRoomMemberRepository(self._session)

        room = await chat_room_repo.find_by_id(room_id)
        if room is None:
            raise ChatRoomNotFoundError("존재하지 않는 방입니다.")

        final_seq = await member_repo.mark_read(room_id, me_id, up_to_server_seq)
        if final_seq is None:
            raise PermissionError("이 방의 활성 멤버가 아닙니다.")

        redis = await get_redis_client()
        await redis.hset(unread_key(me_id), room_id, 0)

        await self._fanout.fan_out_to_session(
            me_session_id,
            {
                "type": "read_ack",
                "room_id": room_id,
                "up_to_server_seq": final_seq,
            },
        )
        await self._fanout.fan_out_to_room(
            room_id,
            {
                "type": "read",
                "user_id": me_id,
                "sender_session_id": me_session_id,
                "up_to_server_seq": final_seq,
            },
        )

        logger.info(
            "읽음 마킹: room_id={}, user_id={}, up_to_seq={}, final_seq={}",
            room_id, me_id, up_to_server_seq, final_seq,
        )
        return final_seq


    # ──────────────────── 내부 helper ────────────────────

    @staticmethod
    async def _get_current_seq(
        message_repo: ChatMessageRepository,
        room_id: str,
    ) -> int:
        """방의 현재 server_seq — Redis 우선, miss 시 Mongo `$max(server_seq)` 폴백 (C2).

        둘 다 비어있으면 0 (아직 첫 메시지 전). 초대 시점의 last_read 기준점으로 사용.
        """
        redis = await get_redis_client()
        raw = await redis.get(room_seq_key(room_id))
        if raw is not None:
            try:
                return int(raw)
            except ValueError:
                pass
        return await message_repo.get_max_server_seq(room_id)


    @staticmethod
    def _to_group_dto(room: ChatRoom) -> ChatRoomData:
        """그룹 방 생성 직후 DTO — peer 는 항상 None, last_message 도 None.

        notification_muted 는 방금 만든 멤버 row 라 NULL → False 로 노출.
        """
        return ChatRoomData(
            chat_room_id=room.chat_room_id,
            type=room.type,
            title=room.title,
            peer=None,
            last_message=None,
            unread_count=0,
            last_message_at=room.last_message_at,
            effective_last_at=room.effective_last_at or room.created_at,
            notification_muted=False,
        )


    # ──────────────────── 내부 변환 ────────────────────

    @staticmethod
    async def _to_dto(room: ChatRoom, me_id: str, peer) -> ChatRoomData:
        """DTO 변환. 신규 1:1 방은 last_message 가 항상 None.

        idempotent 재활용 케이스에도 mute 는 False 로 응답한다 — 직전에 직접 끄는
        UX 가 아니므로 방 생성 응답에서 차단 상태를 보일 필요가 없다고 판단.
        클라이언트는 list/get 으로 정확한 mute 를 다시 받는다.
        """
        # peer 가 User ORM 객체 (User + detail) 로 오는 경우 detail 에서 프로필 추출
        peer_dto = ChatRoomPeerData(
            user_id=peer.user_id,
            user_name=peer.detail.user_name if peer.detail else None,
            profile_image_url=peer.detail.profile_image_url if peer.detail else None,
        )
        return ChatRoomData(
            chat_room_id=room.chat_room_id,
            type=room.type,
            title=room.title,
            peer=peer_dto,
            last_message=None,
            unread_count=0,
            last_message_at=room.last_message_at,
            effective_last_at=room.effective_last_at or room.created_at,
            notification_muted=False,
        )
