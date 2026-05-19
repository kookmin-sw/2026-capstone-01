"""메시지 송신 서비스 — 핫패스 12단계

단계 요약:
    1. 입력 검증 (Pydantic 레벨에서 이미 처리 — 본 서비스는 비즈 검증)
    2. 멤버십 확인 (Redis room:members 캐시 miss-through)
    3. Rate limit (`incr_with_ttl.lua` — INCR+EXPIRE 원자)
    4. 차단 체크 (Phase 2 에서 구체화. Phase 1 은 1:1 방 생성 시점에 이미 차단됨)
    5. dedupe (`SET dedupe:{uid}:{cmid} 1 NX EX 600`)
    6. server_seq 채번 — 2단계 Lua + 키 부재 시 Mongo max 로 복구
    7. Mongo insert + UNIQUE 충돌 시 `force_jump.lua` 로 최대 3회 재시도
    8. RDB last_message_* 갱신 — SAVEPOINT 실패 시 `dirty:chat_room` 에 적재
    9. unread pipeline (`transaction=False` + `min_count > 0` 조건 분기. 시스템 메시지 skip)
    10. fan_out_to_room (발신자 skip 은 FanoutService 내부)
    11. FCM 푸시 (fire-and-forget. 시스템 메시지 skip. 실패해도 ACK 정상)
    12. 발신 세션에 `message.sent` 직송 (ACK)
"""
import random
from pymongo.errors import DuplicateKeyError
from datetime import datetime, timedelta, timezone
import asyncio

from app.util.id_generator import generate_message_id
from app.domain.notification.service.fcm import FcmService
from app.domain.friend.repository.user_block import UserBlockRepository
from app.domain.chat.service.exception import UpstreamError
from app.domain.chat.repository.chat_room import ChatRoomRepository
from app.domain.chat.repository.chat_message import ChatMessageRepository
from app.domain.chat.repository.chat_member import ChatRoomMemberRepository
from app.domain.chat.model.chat_room import ChatRoom, ChatRoomType
from app.domain.chat.model.chat_message import MessageType
from app.domain.chat.dto.message import MessageSentAckData
from app.database.session import UnitOfWork, _current_session, mongodb, transactional
from app.core.redis import get_redis_client, get_redis_dedupe_client
from app.core.logger import get_logger
from app.core.chat.redis_key import (
    DEDUPE_TTL,
    DIRTY_CHAT_ROOM_KEY,
    RATE_LIMIT_THRESHOLD,
    RATE_LIMIT_TTL,
    ROOM_BLOCKS_TTL,
    ROOM_MEMBERS_TTL,
    SEQ_FORCE_JUMP_GAP,
    SEQ_FORCE_JUMP_JITTER_MAX,
    SEQ_RECOVER_GAP,
    dedupe_key,
    rate_msg_key,
    room_blocks_key,
    room_members_key,
    room_seq_key,
    unread_key,
)
from app.core.chat.lua_script import lua_scripts


logger = get_logger("chat.send")


# force_jump / Mongo insert 재시도 상한
_MAX_INSERT_ATTEMPTS = 3

# 메시지 편집 허용 시간 — 카톡과 동일한 5 분 (Phase 2 #5)
EDIT_TIME_LIMIT = timedelta(minutes=5)

# FCM 푸시 본문 미리보기 길이 — 길면 잘라서 "..." 추가.
_PUSH_BODY_PREVIEW_LIMIT = 100

# fire-and-forget 백그라운드 task 핸들 보관소 — Python 가 미참조 task 를 GC 로
# 회수하는 이슈 방지 (asyncio 공식 권장 패턴).
_PUSH_TASKS: set[asyncio.Task] = set()


class MessageService:
    """메시지 송신 핫패스."""

    def __init__(self, uow: UnitOfWork, fanout_service, fcm_service: FcmService):
        self.uow = uow
        self._fanout = fanout_service
        self._fcm = fcm_service


    @transactional
    async def send_message(
        self,
        *,
        sender_user_id: str,
        sender_session_id: str,
        room_id: str,
        client_msg_id: str,
        msg_type: MessageType,
        content: str,
    ) -> MessageSentAckData:
        """WS `op=send` 처리 진입점. ACK DTO 반환. 실패는 예외로 전파."""

        member_repo = ChatRoomMemberRepository(self._session)
        chat_room_repo = ChatRoomRepository(self._session)
        message_repo = ChatMessageRepository(mongodb.database)
        block_repo = UserBlockRepository(self._session)

        redis_hot = await get_redis_client()
        redis_dedupe = await get_redis_dedupe_client()


        # ─── (2) 멤버십 검증 — 캐시 miss 시 RDB 에서 전체 멤버 로드 ───
        await self._ensure_membership(
            redis_hot, member_repo, room_id=room_id, user_id=sender_user_id,
        )


        # ─── (3) Rate limit (Lua 원자) ───
        count = await lua_scripts.incr_with_ttl(
            keys=[rate_msg_key(sender_user_id)],
            args=[RATE_LIMIT_TTL],
        )
        if count > RATE_LIMIT_THRESHOLD:
            raise ValueError("메시지 전송 속도 제한에 걸렸습니다. 잠시 후 다시 시도해주세요.")


        # ─── (4) 차단 체크 — DIRECT 방만 적용. GROUP 은 차단과 메시지 송신이 독립.
        #   - 캐시 miss 시 user_block 양방향 조회 후 SADD 로 miss-through 구성
        #   - 차단 0 건이어도 `__none__` sentinel 로 key 를 존재시켜 miss vs empty 구분
        #   - UNBLOCK 시 friend 도메인이 `BlockCacheService.invalidate_block_cache` 를
        #     호출해 즉시 stale 캐시를 제거 — 해제 후 TTL 대기 없음 (#6).
        room = await chat_room_repo.find_by_id(room_id)
        if room is None:
            raise ValueError("존재하지 않는 방입니다.")
        if room.type == ChatRoomType.DIRECT:
            if await self._is_direct_blocked(
                redis_hot, block_repo, room=room, sender_user_id=sender_user_id,
            ):
                raise PermissionError(
                    "차단 관계인 유저에게는 메시지를 보낼 수 없습니다.",
                )


        # ─── (5) dedupe — NX 로 선점. 이미 있으면 재전송으로 간주하고 중단 ───
        dedupe_k = dedupe_key(sender_user_id, client_msg_id)
        first_time = await redis_dedupe.set(dedupe_k, "1", nx=True, ex=DEDUPE_TTL)
        if not first_time:
            # 재전송. 원본 저장은 이미 끝났으므로 같은 의미로 응답 (저장되진 않음).
            # Phase 2 에서 dedupe 값에 실제 ACK payload 를 저장하는 방식으로 확장 가능.
            raise ValueError("이미 처리된 메시지입니다 (dedupe).")


        # ─── (6)+(7) seq 채번 + Mongo insert ───
        # Mongo 저장 성공이 dedupe 유지의 경계. 이 블록 안 어디서 throw 되든 dedupe 를
        # 풀어 클라가 같은 client_msg_id 로 재시도 가능하게 한다.
        # (이전 구현은 DuplicateKeyError 만 잡아 ConnectionTimeout 등 다른 Mongo 예외 시
        #  dedupe 가 영구 잔존 → 같은 메시지 10분간 차단되는 버그가 있었음.)
        try:
            server_seq = await self._allocate_seq(
                message_repo, redis_hot, room_id=room_id,
            )

            now = datetime.now(timezone.utc)
            message_id = generate_message_id()
            doc = {
                "_id": message_id,
                "chat_room_id": room_id,
                "server_seq": server_seq,
                "sender_id": sender_user_id,
                "type": msg_type.value,
                "content": content,
                "created_at": now,
                "edited_at": None,
                "deleted_at": None,
            }

            for attempt in range(_MAX_INSERT_ATTEMPTS):
                try:
                    await message_repo.insert(doc)
                    break
                except DuplicateKeyError:
                    # seq 강제 점프 — jitter 는 os.urandom 기반 random (main.py 에서 seed)
                    jitter = random.randint(1, SEQ_FORCE_JUMP_JITTER_MAX)
                    new_seq = await lua_scripts.force_jump(
                        keys=[room_seq_key(room_id)],
                        args=[SEQ_FORCE_JUMP_GAP, jitter],
                    )
                    server_seq = int(new_seq)
                    doc["server_seq"] = server_seq
            else:
                logger.error(
                    "메시지 저장 {}회 연속 DuplicateKey: room_id={}, user_id={}",
                    _MAX_INSERT_ATTEMPTS, room_id, sender_user_id,
                )
                raise UpstreamError("메시지 저장에 실패했습니다. 잠시 후 다시 시도해주세요.")

        except Exception:
            await redis_dedupe.delete(dedupe_k)
            raise


        # ─── (8) RDB last_message_* 갱신 — SAVEPOINT 격리 + 실패 시 dirty 큐 ───
        try:
            async with self._session.begin_nested():
                await chat_room_repo.update_last_message(
                    chat_room_id=room_id,
                    message_id=message_id,
                    server_seq=server_seq,
                    at=now,
                )
        except Exception as e:
            logger.warning(
                "last_message_* 갱신 실패 → dirty 큐 적재: room_id={}, err={}",
                room_id, type(e).__name__,
            )
            await redis_hot.sadd(DIRTY_CHAT_ROOM_KEY, room_id)


        # ─── (9) unread 증가 — 발신자 제외. 시스템 메시지는 skip (H3) ───
        if msg_type != MessageType.SYSTEM:
            await self._bump_unread(redis_hot, room_id=room_id, sender_user_id=sender_user_id)


        # ─── (10) 방에 브로드캐스트 — fan-out 내부에서 발신자 skip ───
        await self._fanout.fan_out_to_room(
            room_id,
            {
                "type": "message.new",
                "sender_session_id": sender_session_id,
                "message": {
                    "message_id": message_id,
                    "chat_room_id": room_id,
                    "server_seq": server_seq,
                    "sender_id": sender_user_id,
                    "type": msg_type.value,
                    "content": content,
                    "created_at": now.isoformat(),
                },
            },
        )


        # ─── (11) FCM 푸시 — fire-and-forget. 발신자 ACK 지연을 막기 위해 task 로 분리.
        #   - 시스템 메시지(JOIN/LEAVE/KICK) 는 unread 와 동일하게 skip (H3 일관성)
        #   - 어떤 예외도 비즈에 영향 없음 (helper 가 모든 예외 swallow)
        #   - 트랜잭션 밖에서 실행되지만 단계 7(Mongo) + 10(fanout) 까지 도달했다는 건
        #     메시지가 이미 "출시" 됐다는 뜻 → 후속 롤백은 사실상 발생 안 함.
        if msg_type != MessageType.SYSTEM:
            self._spawn_push_task(
                room_id=room_id,
                sender_user_id=sender_user_id,
                content=content,
            )


        # ─── (12) 발신 세션에 ACK 직송 ───
        return MessageSentAckData(
            client_msg_id=client_msg_id,
            message_id=message_id,
            server_seq=server_seq,
            created_at=now,
        )


    # ──────────────────────────────────────────────────────────
    # 내부 헬퍼
    # ──────────────────────────────────────────────────────────

    @staticmethod
    async def _ensure_membership(
        redis_hot,
        member_repo: ChatRoomMemberRepository,
        *,
        room_id: str,
        user_id: str,
    ) -> None:
        """`room:members:{R}` 캐시를 조회해 멤버십 검증. miss 시 **방 멤버 전체**를 RDB 에서
        한 번에 로드 후 SADD. 퇴장한 유저는 cache miss 가 복원해도 is_left=false
        에서 제외되므로 자연히 차단.
        """
        key = room_members_key(room_id)
        is_member = await redis_hot.sismember(key, user_id)
        if is_member:
            return

        members = await member_repo.find_active_member_ids(room_id)
        if not members:
            raise ValueError("존재하지 않는 방이거나 멤버가 없습니다.")

        pipe = redis_hot.pipeline(transaction=False)
        pipe.sadd(key, *members)
        pipe.expire(key, ROOM_MEMBERS_TTL)
        await pipe.execute()

        if user_id not in members:
            raise PermissionError("이 방의 멤버가 아닙니다.")


    @staticmethod
    async def _allocate_seq(
        message_repo: ChatMessageRepository,
        redis_hot,
        *,
        room_id: str,
    ) -> int:
        """
        핫패스: `incr_fast.lua` → 키가 있으면 INCR 결과 반환, 없으면 -1.
        복구: Mongo max 조회 후 `recover_and_incr.lua` 에 `base = max + SEQ_RECOVER_GAP`
              전달. 진짜 첫 메시지(mongo_max=0) 는 base=0 으로 → 자연스럽게 seq=1.
        """
        seq = await lua_scripts.incr_fast(keys=[room_seq_key(room_id)])
        seq = int(seq)
        if seq != -1:
            return seq

        # 복구 경로
        mongo_max = await message_repo.get_max_server_seq(room_id)
        base = mongo_max + SEQ_RECOVER_GAP if mongo_max > 0 else 0
        recovered = await lua_scripts.recover_and_incr(
            keys=[room_seq_key(room_id)],
            args=[base],
        )
        return int(recovered)


    # ──────────────────────────────────────────────────────────
    # 시스템 메시지 (Phase 2 #2)
    # ──────────────────────────────────────────────────────────

    @transactional
    async def send_system_message(
        self,
        *,
        room_id: str,
        action: str,
        actor_id: str | None,
        target_ids: list[str] | None = None,
        actor_session_id: str | None = None,
    ) -> None:
        """시스템 메시지 기록 — 방 관리 액션(`created`/`join`/`leave`/`kick`)의 타임라인 표시.

        일반 송신 플로우(5.1)의 **6 / 7 / 8 / 10** 단계만 수행:
            - 멤버십 / rate limit / dedupe / unread 증가 모두 skip (H3)
            - `sender_id=None`, `type="system"`, `content={action, actor_id, target_ids?}`
            - `actor_session_id` 가 있으면 fan-out 시 해당 세션 자기 에코를 차단

        실패 시:
            - Mongo 3회 재시도 후에도 실패 → UpstreamError (로그만, RoomService 는 롤백)
            - last_message 갱신 실패 → `dirty:chat_room` 에 방 id 적재 후 진행
        """
        message_repo = ChatMessageRepository(mongodb.database)
        chat_room_repo = ChatRoomRepository(self._session)
        redis_hot = await get_redis_client()

        server_seq = await self._allocate_seq(
            message_repo, redis_hot, room_id=room_id,
        )

        now = datetime.now(timezone.utc)
        message_id = generate_message_id()
        content: dict = {"action": action, "actor_id": actor_id}
        if target_ids:
            content["target_ids"] = list(target_ids)

        doc = {
            "_id": message_id,
            "chat_room_id": room_id,
            "server_seq": server_seq,
            "sender_id": None,
            "type": MessageType.SYSTEM.value,
            "content": content,
            "created_at": now,
            "edited_at": None,
            "deleted_at": None,
        }

        for attempt in range(_MAX_INSERT_ATTEMPTS):
            try:
                await message_repo.insert(doc)
                break
            except DuplicateKeyError:
                jitter = random.randint(1, SEQ_FORCE_JUMP_JITTER_MAX)
                new_seq = await lua_scripts.force_jump(
                    keys=[room_seq_key(room_id)],
                    args=[SEQ_FORCE_JUMP_GAP, jitter],
                )
                server_seq = int(new_seq)
                doc["server_seq"] = server_seq
        else:
            logger.error(
                "시스템 메시지 {}회 연속 실패: room_id={}, action={}",
                _MAX_INSERT_ATTEMPTS, room_id, action,
            )
            raise UpstreamError("시스템 메시지 저장에 실패했습니다.")

        try:
            async with self._session.begin_nested():
                await chat_room_repo.update_last_message(
                    chat_room_id=room_id,
                    message_id=message_id,
                    server_seq=server_seq,
                    at=now,
                )
        except Exception as e:
            logger.warning(
                "시스템 메시지 last_message_* 갱신 실패 → dirty 큐: room_id={}, err={}",
                room_id, type(e).__name__,
            )
            await redis_hot.sadd(DIRTY_CHAT_ROOM_KEY, room_id)

        # (9) unread pipeline 은 H3 에 따라 skip — 시스템 메시지는 미읽음 수를 증가시키지 않는다.

        await self._fanout.fan_out_to_room(
            room_id,
            {
                "type": "message.new",
                "sender_session_id": actor_session_id,
                "message": {
                    "message_id": message_id,
                    "chat_room_id": room_id,
                    "server_seq": server_seq,
                    "sender_id": None,
                    "type": MessageType.SYSTEM.value,
                    "content": content,
                    "created_at": now.isoformat(),
                },
            },
        )

        logger.info(
            "시스템 메시지: room_id={}, action={}, actor={}, seq={}, target_ids={}",
            room_id, action, actor_id, server_seq, target_ids,
        )


    # ──────────────────────────────────────────────────────────
    # 메시지 편집 / 삭제 (Phase 2 #5)
    # ──────────────────────────────────────────────────────────

    @transactional
    async def edit_message(
        self,
        *,
        message_id: str,
        editor_user_id: str,
        editor_session_id: str,
        new_content: str,
    ) -> dict:
        """본인 메시지를 5 분 이내 편집.

        권한 체크 순서:
        1. 메시지 존재
        2. deleted 상태 아님 / 시스템 메시지 아님
        3. 본인 메시지 (sender_id 일치)
        4. 현재도 방의 활성 멤버 (탈퇴 후 돌아와 자기 메시지 편집 차단)
        5. `now - created_at ≤ 5 분`

        Returns:
            `{message_id, content, edited_at}` — REST 응답 preview 용
        """
        member_repo = ChatRoomMemberRepository(self._session)
        message_repo = ChatMessageRepository(mongodb.database)

        doc = await message_repo.find_by_id(message_id)
        if doc is None:
            raise ValueError("존재하지 않는 메시지입니다.")
        if doc.get("deleted_at") is not None:
            raise ValueError("삭제된 메시지는 편집할 수 없습니다.")
        if doc.get("type") == MessageType.SYSTEM.value:
            raise PermissionError("시스템 메시지는 편집할 수 없습니다.")
        if doc.get("sender_id") != editor_user_id:
            raise PermissionError("본인 메시지만 편집할 수 있습니다.")

        room_id = doc["chat_room_id"]
        if not await member_repo.is_active_member(room_id, editor_user_id):
            raise PermissionError("이 방의 활성 멤버가 아닙니다.")

        now = datetime.now(timezone.utc)
        created_at = doc["created_at"]
        # motor 의 tz_aware=True 덕에 created_at 은 항상 tz-aware
        if (now - created_at) > EDIT_TIME_LIMIT:
            raise ValueError("메시지 편집 제한 시간(5분)이 지났습니다.")

        await message_repo.update_content(
            message_id, new_content, edited_at=now,
        )

        await self._fanout.fan_out_to_room(
            room_id,
            {
                "type": "message.updated",
                "sender_session_id": editor_session_id,
                "message_id": message_id,
                "content": new_content,
                "edited_at": now.isoformat(),
            },
        )

        logger.info(
            "메시지 편집: message_id={}, editor={}, room_id={}",
            message_id, editor_user_id, room_id,
        )
        return {"message_id": message_id, "content": new_content, "edited_at": now}


    @transactional
    async def delete_message(
        self,
        *,
        message_id: str,
        deleter_user_id: str,
        deleter_session_id: str,
    ) -> None:
        """본인 메시지 OR 그룹방 creator 의 soft delete.

        권한:
        - 본인 메시지: `sender_id == deleter_user_id`
        - 또는 그룹방 creator: `room.type=GROUP AND room.creator_id=deleter_user_id`
        - 둘 다 **deleter 가 현재 활성 멤버** 여야 유효 (탈퇴한 creator 의 권한은 소멸 — #1 P5)

        시스템 메시지는 삭제 불가 (자동 발행이므로 관리자도 지우지 않음).
        `chat_room.last_message_id` 가 이 메시지면 Phase 3 reconcile job 이 정리 — 여기선 건드리지 않음.
        """
        member_repo = ChatRoomMemberRepository(self._session)
        chat_room_repo = ChatRoomRepository(self._session)
        message_repo = ChatMessageRepository(mongodb.database)

        doc = await message_repo.find_by_id(message_id)
        if doc is None:
            raise ValueError("존재하지 않는 메시지입니다.")
        if doc.get("deleted_at") is not None:
            raise ValueError("이미 삭제된 메시지입니다.")
        if doc.get("type") == MessageType.SYSTEM.value:
            raise PermissionError("시스템 메시지는 삭제할 수 없습니다.")

        room_id = doc["chat_room_id"]
        sender_id = doc.get("sender_id")

        if not await member_repo.is_active_member(room_id, deleter_user_id):
            raise PermissionError("이 방의 활성 멤버가 아닙니다.")

        if sender_id != deleter_user_id:
            room = await chat_room_repo.find_by_id(room_id)
            if room is None:
                raise ValueError("존재하지 않는 방입니다.")
            is_group_creator = (
                room.type == ChatRoomType.GROUP
                and room.creator_id == deleter_user_id
            )
            if not is_group_creator:
                raise PermissionError(
                    "본인 메시지 또는 그룹 방장만 삭제할 수 있습니다.",
                )

        now = datetime.now(timezone.utc)
        await message_repo.soft_delete(message_id, deleted_at=now)

        await self._fanout.fan_out_to_room(
            room_id,
            {
                "type": "message.deleted",
                "sender_session_id": deleter_session_id,
                "message_id": message_id,
                "deleted_at": now.isoformat(),
            },
        )

        logger.info(
            "메시지 삭제: message_id={}, deleter={}, room_id={}, was_own={}",
            message_id, deleter_user_id, room_id, sender_id == deleter_user_id,
        )


    # ──────────────────────────────────────────────────────────
    # 내부 헬퍼 (계속)
    # ──────────────────────────────────────────────────────────

    @staticmethod
    async def _is_direct_blocked(
        redis_hot,
        block_repo: UserBlockRepository,
        *,
        room: ChatRoom,
        sender_user_id: str,
    ) -> bool:
        """1:1 방에서 sender 가 상대에게 메시지 보낼 수 있는지 확인 (차단이면 True).

        Redis `room:blocks:{R}` SET 이 진실의 최전선. 캐시 miss 면 `user_block`
        양방향을 조회해 재구성하고 `__none__` sentinel 로 "차단 없음" 도 명시적으로
        기록한다 (key 존재 = 캐시 채워짐).
        """
        # 상대 user_id 파생 — 탈퇴로 NULL 이면 차단 체크 의미 없음
        peer_id = (
            room.direct_user_b_id
            if room.direct_user_a_id == sender_user_id
            else room.direct_user_a_id
        )
        if peer_id is None:
            return False

        key = room_blocks_key(room.chat_room_id)
        if not await redis_hot.exists(key):
            blocks = await block_repo.find_blocks_between(sender_user_id, peer_id)
            members = (
                [f"{b.blocker_id}:{b.blocked_id}" for b in blocks] or ["__none__"]
            )
            pipe = redis_hot.pipeline(transaction=True)
            pipe.sadd(key, *members)
            pipe.expire(key, ROOM_BLOCKS_TTL)
            await pipe.execute()

        # 양방향 모두 체크 — 한쪽이라도 차단이면 송신 거절
        if await redis_hot.sismember(key, f"{sender_user_id}:{peer_id}"):
            return True
        if await redis_hot.sismember(key, f"{peer_id}:{sender_user_id}"):
            return True
        return False


    @staticmethod
    async def _bump_unread(redis_hot, *, room_id: str, sender_user_id: str) -> None:
        """방 멤버 전체 (발신자 제외) unread HINCRBY 를 pipeline 으로 1 RTT.

        transaction=False — 100명 방에서도 Redis single-thread 가 다른 명령을 블로킹하지
        않도록 비원자 배치. 실패해도 치명적이지 않음 (Phase 3 의 복구 경로로 수렴).
        """
        key = room_members_key(room_id)
        members = await redis_hot.smembers(key)
        recipients = [uid for uid in members if uid != sender_user_id]
        if not recipients:
            return

        pipe = redis_hot.pipeline(transaction=False)
        for uid in recipients:
            pipe.hincrby(unread_key(uid), room_id, 1)
        try:
            await pipe.execute()
        except Exception as e:
            logger.warning(
                "unread pipeline 실패 (무시하고 진행): room_id={}, err={}",
                room_id, type(e).__name__,
            )


    # ──────────────────────────────────────────────────────────
    # FCM 푸시 (fire-and-forget)
    # ──────────────────────────────────────────────────────────

    def _spawn_push_task(
        self, *, room_id: str, sender_user_id: str, content: str,
    ) -> None:
        """푸시 task 를 백그라운드로 띄움. 모듈 레벨 set 에 핸들 보관해 GC 회수 방지."""
        task = asyncio.create_task(
            self._push_chat_to_recipients(
                room_id=room_id,
                sender_user_id=sender_user_id,
                content=content,
            )
        )
        _PUSH_TASKS.add(task)
        task.add_done_callback(_PUSH_TASKS.discard)


    async def _push_chat_to_recipients(
        self, *, room_id: str, sender_user_id: str, content: str,
    ) -> None:
        """발신자 제외한 방 멤버 전체에게 FCM 푸시 multicast.

        fire-and-forget 컨텍스트 — 어떤 예외도 raise 하지 않는다.
        FcmService 의 bulk send_chat_push 가 N 명을 한 트랜잭션 + 한 multicast 로
        fan-out 하므로 여기선 단순히 recipients 한 번에 넘긴다.
        """
        # create_task 는 부모 Context 를 복사하므로 _current_session 에 부모(이미 닫힌)
        # 세션이 박혀있다. 명시적으로 끊어줘야 send_chat_push 의 @transactional 이
        # 좀비 세션에 "참여" 하지 않고 자기 own UoW 로 새 트랜잭션을 연다.
        _current_session.set(None)
        try:
            redis_hot = await get_redis_client()
            members = await redis_hot.smembers(room_members_key(room_id))
            recipients = [uid for uid in members if uid != sender_user_id]
            if not recipients:
                return

            body = (
                content[:_PUSH_BODY_PREVIEW_LIMIT] + "..."
                if len(content) > _PUSH_BODY_PREVIEW_LIMIT
                else content
            )

            # title 미지정 — FcmService 가 sender_id 로 발신자 user_name 을 조회해 채우고
            # 탈퇴/detail 결손 시 "새 메시지" 로 폴백. 한 트랜잭션 안에서 PK 1회 조회라 비용 무시.
            await self._fcm.send_chat_push(
                user_ids=recipients,
                chat_room_id=room_id,
                sender_id=sender_user_id,
                body=body,
            )
        except Exception as e:
            logger.warning(
                "FCM 푸시 helper 실패 (무시): room_id={}, err={}",
                room_id, type(e).__name__,
            )
