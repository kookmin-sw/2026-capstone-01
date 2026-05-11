"""채팅 도메인 백그라운드 reconcile / recover 작업.

두 가지 기능:

1. `reconcile_last_message_once()` — **5분 주기** 로 `dirty:chat_room` SET 을 소진하며
   `chat_room.last_message_*` 역정규화 필드를 Mongo 진실값으로 맞춤.
   메시지 송신 경로에서 RDB UPDATE 가 SAVEPOINT 내 실패 시 방 ID 가 SET 에 적재되는데,
   이 워커가 주기적으로 수렴시킨다.

2. `recover_unread_for_user()` — WS 재접속 시 `unread:{uid}` HASH 가 비어있으면
   RDB 의 `last_read_*` + Mongo 의 메시지 수를 기반으로 재계산. Redis flush/장애로
   카운터가 유실된 뒤 복구 경로.

`main.py` lifespan 에서 `start_reconcile_scheduler(session_factory)` 를 1 회 호출,
shutdown 시 `stop_reconcile_scheduler()` 호출. `recover_unread_for_user` 는 ws.py 가
직접 호출 — 두 기능 모두 같은 session_factory 공유.
"""
from __future__ import annotations
from typing import Optional
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
import os
import asyncio

from app.domain.chat.repository.chat_member import ChatRoomMemberRepository
from app.domain.chat.repository.chat_message import ChatMessageRepository
from app.domain.chat.repository.chat_room import ChatRoomRepository
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


# ──────────────────── 튜닝 상수 ────────────────────

# reconcile 배치 — SPOP count. 너무 크면 Mongo aggregate 페이로드 비대 + 단일 루프 tick 이
# 길어져 shutdown stop_event 반응이 늦음.
RECONCILE_BATCH_SIZE = 500

# reconcile 주기. alarm SLO 15분 보다 충분히 짧게 5분.
# `CHAT_RECONCILE_INTERVAL_SEC` env 로 override — smoke/개발에서 1~2초로 줄여 E2E 검증 가능.
RECONCILE_INTERVAL_SEC = int(os.getenv("CHAT_RECONCILE_INTERVAL_SEC", "300"))

# shutdown 시 루프가 stop_event 감지 후 현재 배치까지 마치는 데 줄 최대 유예.
RECONCILE_SHUTDOWN_GRACE_SEC = 10.0

# unread 복구 — Mongo count 동시성. 한 유저 재접속당 방 수십 개 × 서버 전체 동시 재접속
# 가능 → 제한 없이 돌면 Mongo 부하 폭주.
UNREAD_MONGO_CONCURRENCY = 10

# 카톡 관례: 999+ 로 캡. 클라는 999 이상을 "999+" 로 렌더링.
UNREAD_COUNT_CAP = 999

# count_documents limit — cap 보다 1 큰 값으로 충분 (더 세도 무시).
UNREAD_COUNT_LIMIT = UNREAD_COUNT_CAP + 1


# ──────────────────── 모듈 상태 ────────────────────

# main.py lifespan 에서 1 회 주입. 테스트/스크립트도 여기에 직접 주입 가능.
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

# 주기 루프 핸들 — 중복 시작 방지 + graceful shutdown 용.
_reconcile_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


def _require_factory() -> async_sessionmaker[AsyncSession]:
    """lifespan 초기화 전에 호출되면 즉시 실패 (조용한 nohup 방지)."""
    if _session_factory is None:
        raise RuntimeError(
            "chat reconcile 워커가 초기화되지 않았습니다. "
            "main.py lifespan 에서 start_reconcile_scheduler(session_factory) 를 먼저 호출하세요.",
        )
    return _session_factory


# ──────────────────── reconcile_last_message ────────────────────

async def reconcile_last_message_once() -> int:
    """`dirty:chat_room` 에서 한 배치(최대 `RECONCILE_BATCH_SIZE`) 를 pop 해 정합성 복구.

    Returns:
        이번 호출에서 pop 한 방 개수. 0 이면 SET 비어있음 (주기 루프에서 `< BATCH_SIZE`
        를 보고 drain 중단 신호로 사용).
    """
    redis_hot = await get_redis_client()

    # 매 tick 시작 시 dirty SET 사이즈 측정 — 적체 인지 신호.
    chat_reconcile_dirty_set_size_set(await redis_hot.scard(DIRTY_CHAT_ROOM_KEY))

    async with chat_reconcile_tick():
        # SPOP count=N — Redis 3.2+ 지원. redis-py 는 count 인자 있으면 list 반환.
        popped = await redis_hot.spop(DIRTY_CHAT_ROOM_KEY, RECONCILE_BATCH_SIZE)
        if not popped:
            chat_reconcile_batch_pop_inc("empty")
            return 0
        # count 없이 호출한 경로와 통일성 유지 (redis-py 버전 diff 방어).
        room_ids: list[str] = list(popped) if isinstance(popped, (list, set)) else [popped]
        if not room_ids:
            chat_reconcile_batch_pop_inc("empty")
            return 0

        # Mongo aggregate — 방별 최신 메시지 1건
        message_repo = ChatMessageRepository(mongodb.database)
        try:
            last_by_room = await message_repo.find_last_by_rooms(room_ids)
        except Exception as e:
            # Mongo 쪽 장애면 이번 배치를 통째로 되돌려 다음 tick 에서 재시도
            chat_reconcile_batch_pop_inc("mongo_failed")
            logger.warning(
                "reconcile: Mongo aggregate 실패 → {} 개 방 재적재: {}",
                len(room_ids), type(e).__name__,
            )
            await redis_hot.sadd(DIRTY_CHAT_ROOM_KEY, *room_ids)
            return 0

        if not last_by_room:
            # Mongo 에 메시지가 하나도 없는 이상 상태 — 방 생성 직후 삭제된 경우 등.
            # 이 상태에선 last_message_* 가 NULL 인 게 정상이라 UPDATE 없이 pop 결과만 흘려보냄.
            chat_reconcile_batch_pop_inc("ok")
            chat_reconcile_rooms_processed_inc("skipped", len(room_ids))
            logger.info(
                "reconcile: pop={} 이지만 Mongo hit 0 — last_message 없는 방으로 간주하고 skip",
                len(room_ids),
            )
            return len(room_ids)

        # RDB UPDATE — 각 방마다 regress 가드 + 실패 시 재큐잉
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
                # commit 실패면 배치 전체 다시 돌림. async with factory() 의 __aexit__ 는
                # 예외가 블록 밖으로 나가지 않으면 auto-rollback 하지 않으므로 명시적으로 rollback.
                # 방치하면 커넥션이 aborted 트랜잭션 상태로 풀에 반납될 위험.
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

        # batch result 분류:
        #   - rdb_failed: commit 통째 실패 — 배치 전체 재적재 (rooms outcome 은 0)
        #   - ok        : commit 성공 (partial UPDATE 실패는 outcome=failed 로 별도 카운트)
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
    """주기 루프 — stop_event 가 set 될 때까지 무한 반복."""
    logger.info(
        "reconcile 루프 시작: interval={}s, batch={}",
        RECONCILE_INTERVAL_SEC, RECONCILE_BATCH_SIZE,
    )
    while not stop_event.is_set():
        # 적체 drain — 한 사이클 내에 연속 pop. 배치 full 이면 바로 다음 배치 (백로그 해소).
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

        # 다음 tick 까지 대기 — stop_event set 되면 즉시 깨어남
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=RECONCILE_INTERVAL_SEC)
            break
        except asyncio.TimeoutError:
            pass

    logger.info("reconcile 루프 종료")


# ──────────────────── recover_unread_for_user ────────────────────

async def recover_unread_for_user(
    user_id: str,
    only_room: Optional[str] = None,
) -> dict[str, int]:
    """DB 기준으로 `unread:{user_id}` HASH 를 재계산 후 HSET.

    Redis flush/장애 또는 재초대 직후 호출. `get_unread_counts` 가 빈 dict 를 반환했을 때
    ws.py 가 백그라운드 태스크로 trigger 하도록 설계.

    알고리즘:
        1) RDB: 유저의 (활성) 방 별 `last_read_message_server_seq` 조회
        2) Mongo: 방 별 `server_seq > last_read` 메시지 개수 count (semaphore 10)
        3) Redis: HSET unread:{uid} {room_id} min(count, 999) 일괄

    Args:
        user_id: 복구 대상 유저
        only_room: 특정 방만 복구 (재초대 플로우 등). None 이면 유저 전체 방.

    Returns:
        `{room_id: unread_count}` — Redis 에 반영된 실제 값 (0 포함). 호출측이 이 값을
        `unread_synced` 이벤트로 클라에 push 할 수 있다.
    """
    factory = _require_factory()

    # 1. RDB
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

    # 2. Mongo — semaphore 로 동시 요청 제한
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

    # 3. Redis 일괄 HSET — 실패한 방은 skip (다음 복구 기회)
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
            # 파이프라인은 중간 명령이 실패해도 **이전 명령들은 Redis 에 반영된 상태**.
            # partial state 로 남으면 다음 재연결 시 `get_unread_counts` 가 non-empty 를
            # 반환해 **복구가 재시도되지 않음** → 빠진 방들의 historical unread 영구 유실.
            # DEL 로 전체를 쓸어 EXISTS=0 을 강제해야 다음 연결에서 recovery 가 재trigger.
            logger.warning(
                "recover_unread: Redis 반영 실패 — partial state 정리 후 counts 취소: "
                "user_id={}, err={}",
                user_id, e,
            )
            cleanup_ok = True
            try:
                await redis_hot.delete(unread_key(user_id))
            except Exception as del_err:
                # DEL 도 실패면 partial state 가 남지만 이미 최선은 다한 상태.
                # 다음 재연결에서 `get_unread_counts` non-empty 일 수 있고, 일부 방 unread 유실.
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


# ──────────────────── 스케줄러 훅 ────────────────────

def start_reconcile_scheduler(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """앱 startup 에서 1 회 호출. 주기 reconcile 루프 시작 + 워커 전역 의존성 주입.

    `recover_unread_for_user` 도 같은 `session_factory` 를 공유하므로 반드시 이 함수가
    먼저 호출되어야 한다 (ws.py 의 호출 경로보다 lifespan startup 이 앞섬).
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
    """앱 shutdown 에서 호출. 루프를 graceful 종료하되 `GRACE_SEC` 초과 시 cancel.

    현재 tick 이 Mongo aggregate 중이면 짧게 기다렸다가 강제 취소 — DB 쪽 쿼리는 그쪽
    timeout 에 의존. 무한 대기는 배포 블로킹을 유발하므로 명시적 grace 도입.
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
