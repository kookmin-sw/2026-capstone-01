"""채팅 백그라운드 reconcile / recover.

- `reconcile_last_message_once`: 5분 주기로 `dirty:chat_room` SET 을 소진하며
  `chat_room.last_message_*` 역정규화 필드를 Mongo 진실값으로 수렴.
- `recover_unread_for_user`: WS 재접속 시 `unread:{uid}` HASH 가 비면 RDB `last_read_*` +
  Mongo 메시지 수로 재계산. Redis flush/장애 후 복구 경로.
"""
from __future__ import annotations

from typing import Optional
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
import os
import asyncio

from app.domain.chat.repository.chat_room import ChatRoomRepository
from app.domain.chat.repository.chat_message import ChatMessageRepository
from app.domain.chat.repository.chat_member import ChatRoomMemberRepository
from app.database.session import mongodb
from app.core.redis import get_redis_client
from app.core.logger import get_logger
from app.core.instrumentation import (
    chat_reconcile_batch_pop_inc,
    chat_reconcile_dirty_set_size_set,
    chat_reconcile_rooms_processed_inc,
    chat_reconcile_tick,
    chat_unread_recover_inc,
    worker_tick,
)
from app.core.chat.redis_key import DIRTY_CHAT_ROOM_KEY, unread_key


logger = get_logger("chat.reconcile")


# 너무 크면 Mongo aggregate 페이로드 비대 + tick 길어져 shutdown 반응 느려짐.
RECONCILE_BATCH_SIZE = 500

# alarm SLO 15분보다 충분히 짧게. env 로 override (smoke/개발에서 1~2초로 줄임).
RECONCILE_INTERVAL_SEC = int(os.getenv("CHAT_RECONCILE_INTERVAL_SEC", "300"))

RECONCILE_SHUTDOWN_GRACE_SEC = 10.0

# 재접속당 방 수십 개 × 동시 재접속이면 Mongo 부하 폭주 — semaphore 로 제한.
UNREAD_MONGO_CONCURRENCY = 10

# 카톡 관례 — 999+ 캡.
UNREAD_COUNT_CAP = 999
UNREAD_COUNT_LIMIT = UNREAD_COUNT_CAP + 1


# main.py lifespan 에서 1회 주입.
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

_reconcile_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


def _require_factory() -> async_sessionmaker[AsyncSession]:
    """lifespan 초기화 전 호출 시 즉시 실패."""
    if _session_factory is None:
        raise RuntimeError(
            "chat reconcile 워커가 초기화되지 않았습니다. "
            "main.py lifespan 에서 start_reconcile_scheduler(session_factory) 를 먼저 호출하세요.",
        )
    return _session_factory


async def reconcile_last_message_once() -> int:
    """`dirty:chat_room` 에서 한 배치 pop 후 RDB `last_message_*` 를 Mongo 값으로 갱신.

    Returns:
        이번 호출에서 pop 한 방 개수. `< BATCH_SIZE` 면 drain 중단 신호로 사용.
    """
    redis_hot = await get_redis_client()

    chat_reconcile_dirty_set_size_set(await redis_hot.scard(DIRTY_CHAT_ROOM_KEY))

    async with chat_reconcile_tick():
        # SPOP count — redis-py 는 count 인자가 있으면 list 반환.
        popped = await redis_hot.spop(DIRTY_CHAT_ROOM_KEY, RECONCILE_BATCH_SIZE)
        if not popped:
            chat_reconcile_batch_pop_inc("empty")
            return 0
        room_ids: list[str] = list(popped) if isinstance(popped, (list, set)) else [popped]
        if not room_ids:
            chat_reconcile_batch_pop_inc("empty")
            return 0

        message_repo = ChatMessageRepository(mongodb.database)
        try:
            last_by_room = await message_repo.find_last_by_rooms(room_ids)
        except Exception as e:
            chat_reconcile_batch_pop_inc("mongo_failed")
            logger.warning(
                "reconcile: Mongo aggregate 실패 → {} 개 방 재적재: {}",
                len(room_ids), type(e).__name__,
            )
            await redis_hot.sadd(DIRTY_CHAT_ROOM_KEY, *room_ids)
            return 0

        if not last_by_room:
            # Mongo 메시지 0 — 방 생성 직후 삭제 등의 이상 상태. UPDATE 없이 결과만 흘려보냄.
            chat_reconcile_batch_pop_inc("ok")
            chat_reconcile_rooms_processed_inc("skipped", len(room_ids))
            logger.info(
                "reconcile: pop={} 이지만 Mongo hit 0 — last_message 없는 방으로 간주하고 skip",
                len(room_ids),
            )
            return len(room_ids)

        factory = _require_factory()
        failed: list[str] = []
        updated = 0
        commit_failed = False
        async with factory() as session:
            chat_room_repo = ChatRoomRepository(session)
            for room_id, doc in last_by_room.items():
                try:
                    await chat_room_repo.update_last_message_if_greater(
                        chat_room_id=room_id,
                        message_id=doc["message_id"],
                        server_seq=doc["server_seq"],
                        at=doc["created_at"],
                    )
                    updated += 1
                except Exception as e:
                    logger.warning(
                        "reconcile: 방 {} UPDATE 실패 — 재적재: {}",
                        room_id, type(e).__name__,
                    )
                    failed.append(room_id)
            try:
                await session.commit()
            except Exception as e:
                # commit 실패 시 명시 rollback — `async with` 가 자동 rollback 하지 않으면
                # 커넥션이 aborted 트랜잭션 상태로 풀에 반납될 위험.
                logger.warning(
                    "reconcile: commit 실패 → 배치 전체 재적재 ({} 개): {}",
                    len(last_by_room), type(e).__name__,
                )
                try:
                    await session.rollback()
                except Exception as rb_err:
                    logger.warning(
                        "reconcile: rollback 도 실패 (커넥션 풀 보호 실패 가능): {}",
                        type(rb_err).__name__,
                    )
                failed.extend(last_by_room.keys() - set(failed))
                updated = 0
                commit_failed = True

        if failed:
            await redis_hot.sadd(DIRTY_CHAT_ROOM_KEY, *failed)

        if commit_failed:
            chat_reconcile_batch_pop_inc("rdb_failed")
        else:
            chat_reconcile_batch_pop_inc("ok")
            chat_reconcile_rooms_processed_inc("updated", updated)
            chat_reconcile_rooms_processed_inc("failed", len(failed))

        logger.info(
            "reconcile: pop={}, mongo_hit={}, updated={}, requeued={}",
            len(room_ids), len(last_by_room), updated, len(failed),
        )
        return len(room_ids)


async def _reconcile_loop(stop_event: asyncio.Event) -> None:
    """stop_event 가 set 될 때까지 무한 반복. 한 사이클 내 백로그 drain 후 다음 tick 대기."""
    logger.info(
        "reconcile 루프 시작: interval={}s, batch={}",
        RECONCILE_INTERVAL_SEC, RECONCILE_BATCH_SIZE,
    )
    while not stop_event.is_set():
        try:
            async with worker_tick("reconcile"):
                while True:
                    processed = await reconcile_last_message_once()
                    if processed < RECONCILE_BATCH_SIZE:
                        break
                    if stop_event.is_set():
                        break
        except Exception as e:
            logger.exception("reconcile tick 전역 실패 (계속 진행): {}", e)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=RECONCILE_INTERVAL_SEC)
            break
        except asyncio.TimeoutError:
            pass

    logger.info("reconcile 루프 종료")


async def recover_unread_for_user(
    user_id: str,
    only_room: Optional[str] = None,
) -> dict[str, int]:
    """DB 기준으로 `unread:{user_id}` HASH 재계산 후 HSET.

    Redis flush/장애 또는 재초대 후 호출. ws.py 가 백그라운드 태스크로 트리거.

    Args:
        only_room: 특정 방만 복구 (재초대 등). None 이면 유저 전체 방.

    Returns:
        Redis 에 반영된 `{room_id: count}` (0 포함). 실패 시 빈 dict.
    """
    factory = _require_factory()

    async with factory() as session:
        member_repo = ChatRoomMemberRepository(session)
        last_reads = await member_repo.find_last_read_seqs(
            user_id,
            room_ids=[only_room] if only_room else None,
        )

    if not last_reads:
        chat_unread_recover_inc("ok")
        logger.info(
            "recover_unread: user_id={}, only_room={} — 활성 방 없음, skip",
            user_id, only_room,
        )
        return {}

    sem = asyncio.Semaphore(UNREAD_MONGO_CONCURRENCY)
    message_repo = ChatMessageRepository(mongodb.database)

    async def _count(room_id: str, last_read: int) -> tuple[str, int]:
        async with sem:
            raw = await message_repo.count_after_seq(
                chat_room_id=room_id,
                after_seq=last_read,
                limit=UNREAD_COUNT_LIMIT,
            )
            return room_id, min(raw, UNREAD_COUNT_CAP)

    results = await asyncio.gather(
        *(_count(rid, seq) for rid, seq in last_reads.items()),
        return_exceptions=True,
    )

    counts: dict[str, int] = {}
    for item in results:
        if isinstance(item, BaseException):
            logger.warning("recover_unread: user_id={} 방 count 실패: {}", user_id, item)
            continue
        room_id, cnt = item
        counts[room_id] = cnt

    if counts:
        redis_hot = await get_redis_client()
        pipe = redis_hot.pipeline(transaction=False)
        for rid, cnt in counts.items():
            pipe.hset(unread_key(user_id), rid, cnt)
        try:
            await pipe.execute()
        except Exception as e:
            # pipeline 중간 실패해도 이전 명령은 이미 반영됨 — partial state 로 남으면 다음
            # 재연결 시 `get_unread_counts` 가 non-empty 라 복구 재시도가 안 됨. DEL 로
            # 전체 쓸어 EXISTS=0 을 강제해야 재trigger 된다.
            logger.warning(
                "recover_unread: Redis 반영 실패 — partial state 정리 후 counts 취소: "
                "user_id={}, err={}",
                user_id, e,
            )
            cleanup_ok = True
            try:
                await redis_hot.delete(unread_key(user_id))
            except Exception as del_err:
                cleanup_ok = False
                logger.warning(
                    "recover_unread: cleanup DEL 실패 — partial state 잔존 위험: {}",
                    type(del_err).__name__,
                )
            chat_unread_recover_inc("redis_failed" if cleanup_ok else "cleanup_failed")
            logger.info(
                "recover_unread: user_id={}, rooms={}, recovered=0 (redis 실패)",
                user_id, len(last_reads),
            )
            return {}

    chat_unread_recover_inc("ok")
    logger.info(
        "recover_unread: user_id={}, rooms={}, recovered={}, only_room={}",
        user_id, len(last_reads), len(counts), only_room,
    )
    return counts


def start_reconcile_scheduler(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """앱 startup 1회 — 주기 루프 시작 + 워커 전역 의존성 주입.

    `recover_unread_for_user` 도 같은 factory 를 공유하므로 ws.py 호출보다 먼저 실행되어야 한다.
    """
    global _session_factory, _reconcile_task, _stop_event

    _session_factory = session_factory

    if _reconcile_task is not None and not _reconcile_task.done():
        logger.warning("reconcile 스케줄러 중복 시작 무시")
        return

    _stop_event = asyncio.Event()
    _reconcile_task = asyncio.create_task(
        _reconcile_loop(_stop_event),
        name="chat-reconcile",
    )


async def stop_reconcile_scheduler() -> None:
    """앱 shutdown — graceful 종료 후 `GRACE_SEC` 초과 시 cancel.

    Mongo aggregate 중이면 짧게 기다리고 강제 취소 — 무한 대기는 배포 블로킹.
    """
    global _reconcile_task, _stop_event

    task = _reconcile_task
    event = _stop_event
    _reconcile_task = None
    _stop_event = None

    if task is None or event is None:
        return

    event.set()
    try:
        await asyncio.wait_for(task, timeout=RECONCILE_SHUTDOWN_GRACE_SEC)
    except asyncio.TimeoutError:
        logger.warning(
            "reconcile 루프가 {}s 내에 종료되지 않아 강제 취소",
            RECONCILE_SHUTDOWN_GRACE_SEC,
        )
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    except Exception as e:
        logger.warning("reconcile 루프 종료 대기 중 예외: {}", e)
