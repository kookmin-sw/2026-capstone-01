"""메시지 송신 / 편집 / 삭제 서비스."""
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


_MAX_INSERT_ATTEMPTS = 3
EDIT_TIME_LIMIT = timedelta(minutes=5)
_PUSH_BODY_PREVIEW_LIMIT = 100

# fire-and-forget task 핸들 보관 — GC 가 미참조 task 를 회수하지 않도록.
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
        """WS `op=send` 처리 — ACK DTO 반환, 실패는 예외로 전파."""

        member_repo = ChatRoomMemberRepository(self._session)
        chat_room_repo = ChatRoomRepository(self._session)
        message_repo = ChatMessageRepository(mongodb.database)
        block_repo = UserBlockRepository(self._session)

        redis_hot = await get_redis_client()
        redis_dedupe = await get_redis_dedupe_client()

        await self._ensure_membership(
            redis_hot, member_repo, room_id=room_id, user_id=sender_user_id,
        )

        count = await lua_scripts.incr_with_ttl(
            keys=[rate_msg_key(sender_user_id)],
            args=[RATE_LIMIT_TTL],
        )
        if count > RATE_LIMIT_THRESHOLD:
            raise ValueError("메시지 전송 속도 제한에 걸렸습니다. 잠시 후 다시 시도해주세요.")

        # 차단 체크는 DIRECT 방만 — GROUP 은 차단과 송신이 독립.
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

        # dedupe — NX 선점. 이미 있으면 재전송으로 간주.
        dedupe_k = dedupe_key(sender_user_id, client_msg_id)
        first_time = await redis_dedupe.set(dedupe_k, "1", nx=True, ex=DEDUPE_TTL)
        if not first_time:
            raise ValueError("이미 처리된 메시지입니다 (dedupe).")

        # Mongo 저장 성공이 dedupe 유지의 경계 — 이 블록에서 어떤 예외든 dedupe 를 풀어
        # 클라가 같은 client_msg_id 로 재시도 가능하게 한다.
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

        # last_message_* 갱신 실패는 dirty 큐로 — reconcile 이 수렴시킨다.
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

        # 시스템 메시지는 unread 증가 / 푸시 모두 skip.
        if msg_type != MessageType.SYSTEM:
            await self._bump_unread(redis_hot, room_id=room_id, sender_user_id=sender_user_id)

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

        # FCM 푸시는 fire-and-forget — ACK 지연 차단. 트랜잭션 밖이지만 fanout 까지 도달한
        # 시점에 메시지는 사실상 "출시" 상태라 후속 롤백 없음.
        if msg_type != MessageType.SYSTEM:
            self._spawn_push_task(
                room_id=room_id,
                sender_user_id=sender_user_id,
                content=content,
            )

        return MessageSentAckData(
            client_msg_id=client_msg_id,
            message_id=message_id,
            server_seq=server_seq,
            created_at=now,
        )


    @staticmethod
    async def _ensure_membership(
        redis_hot,
        member_repo: ChatRoomMemberRepository,
        *,
        room_id: str,
        user_id: str,
    ) -> None:
        """`room:members:{R}` 캐시로 멤버십 검증. miss 시 방 멤버 전체를 RDB 로드 후 SADD."""
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
        """핫: `incr_fast.lua`. 키 부재 시 Mongo `max(server_seq)` + `SEQ_RECOVER_GAP` 로 복구."""
        seq = await lua_scripts.incr_fast(keys=[room_seq_key(room_id)])
        seq = int(seq)
        if seq != -1:
            return seq

        mongo_max = await message_repo.get_max_server_seq(room_id)
        base = mongo_max + SEQ_RECOVER_GAP if mongo_max > 0 else 0
        recovered = await lua_scripts.recover_and_incr(
            keys=[room_seq_key(room_id)],
            args=[base],
        )
        return int(recovered)


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
        """방 관리 액션 (`created`/`join`/`leave`/`kick`) 의 타임라인 시스템 메시지 기록.

        멤버십 / rate limit / dedupe / unread 증가 모두 skip.
        `actor_session_id` 가 있으면 해당 세션 자기 에코를 차단.
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


    @transactional
    async def edit_message(
        self,
        *,
        message_id: str,
        editor_user_id: str,
        editor_session_id: str,
        new_content: str,
    ) -> dict:
        """본인 메시지를 5분 이내 편집. 시스템 메시지 / 삭제된 메시지 / 비활성 멤버는 거절."""
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
        """본인 메시지 또는 그룹방 creator 의 soft delete.

        탈퇴한 creator 는 권한 소멸 — 현재 활성 멤버여야만 유효.
        시스템 메시지는 삭제 불가.
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


    @staticmethod
    async def _is_direct_blocked(
        redis_hot,
        block_repo: UserBlockRepository,
        *,
        room: ChatRoom,
        sender_user_id: str,
    ) -> bool:
        """1:1 방에서 양방향 차단 체크 — 한쪽이라도 차단이면 True.

        캐시 miss 시 양방향 `user_block` 조회 후 SADD. 차단 0 건이어도 `__none__` sentinel
        로 key 를 존재시켜 miss vs empty 를 구분한다.
        """
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

        if await redis_hot.sismember(key, f"{sender_user_id}:{peer_id}"):
            return True
        if await redis_hot.sismember(key, f"{peer_id}:{sender_user_id}"):
            return True
        return False


    @staticmethod
    async def _bump_unread(redis_hot, *, room_id: str, sender_user_id: str) -> None:
        """방 멤버 (발신자 제외) unread HINCRBY 를 pipeline 1 RTT 로.

        `transaction=False` — 100명 방에서도 Redis single-thread 가 블로킹되지 않게.
        실패는 무시 (reconcile 경로로 수렴).
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


    def _spawn_push_task(
        self, *, room_id: str, sender_user_id: str, content: str,
    ) -> None:
        """푸시 task 를 백그라운드로 spawn. 모듈 set 에 핸들 보관해 GC 회수 방지."""
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
        """발신자 제외 방 멤버 전체에 FCM 푸시. 어떤 예외도 raise 하지 않는다."""
        # create_task 가 부모 Context 를 복사하므로 _current_session 에 이미 닫힌 부모 세션이
        # 박혀있다. 명시적으로 끊어줘야 send_chat_push 의 @transactional 이 좀비 세션에
        # join 하지 않고 자기 UoW 로 새 트랜잭션을 연다.
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

            # title 은 FcmService 가 sender_id 로 user_name 조회해 채움 (결손 시 "새 메시지" 폴백).
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
