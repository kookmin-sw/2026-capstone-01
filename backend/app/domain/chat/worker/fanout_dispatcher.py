"""채팅 fan-out Pub/Sub 디스패처.

`FANOUT_MODE=node_channel` 모드에서 lifespan startup 시 1회 시작. `node:{NODE_ID}` 채널을
SUBSCRIBE 해 envelope 을 받고 `FanoutService.dispatch_envelope` 으로 라우팅.

ordering: 동일 채널 내 메시지는 publish 순서대로 전달 — 디스패처도 직렬 처리해 이 보장을
깨지 않는다 ("subscribe → fan_out" 순서 보존).

startup race 차단: `start_fanout_dispatcher` 는 `pubsub.subscribe` 가 확정된 뒤 반환해야
한다. main.py 가 그 다음에 ZSET 에 자기 노드를 등록하므로, 반대 순서면 다른 노드의 publish
가 SUBSCRIBE 전에 도달해 누락된다.
"""
from __future__ import annotations

from typing import Optional
import json
import asyncio

from app.domain.chat.service.fanout import FanoutService
from app.core.redis import get_redis_client
from app.core.logger import get_logger
from app.core.instrumentation import chat_fanout_dispatch_alive, worker_tick
from app.core.chat.redis_key import node_channel_key
from app.config.setting import settings


logger = get_logger("chat.fanout_dispatcher")


# `pubsub.get_message` 폴링 간격. 짧으면 shutdown 반응성 좋고, 길면 idle CPU 절감.
DISPATCHER_POLL_TIMEOUT_SEC = 1.0

# pubsub 자체 장애 시 backoff (로그 폭주 방지).
DISPATCHER_ERROR_BACKOFF_SEC = 1.0

# shutdown 시 stop_event 감지 후 unsubscribe 까지 마치는 데 줄 유예.
DISPATCHER_SHUTDOWN_GRACE_SEC = 5.0


_dispatcher_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


async def _dispatch_loop(
    pubsub,
    fanout: FanoutService,
    stop_event: asyncio.Event,
) -> None:
    """SUBSCRIBE 된 pubsub 으로 envelope 직렬 처리.

    pubsub 장애 (Redis 재시작 등) 시 backoff 후 재시도 — cancel 전엔 절대 종료되지 않도록
    모든 예외를 흡수한다. 종료는 stop_event + while 조건 단일 진입점.
    """
    channel = node_channel_key(settings.NODE_ID)

    try:
        while not stop_event.is_set():
            try:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=DISPATCHER_POLL_TIMEOUT_SEC,
                )
            except Exception as e:
                logger.warning(
                    "Pub/Sub get_message 실패 — backoff 후 재시도: {}",
                    type(e).__name__,
                )
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=DISPATCHER_ERROR_BACKOFF_SEC,
                    )
                except asyncio.TimeoutError:
                    pass
                continue

            # liveness — envelope 0 건이어도 polling 살아있는 한 last_tick 갱신.
            chat_fanout_dispatch_alive()

            if msg is None:
                continue
            if msg.get("type") != "message":
                # subscribe ACK 등 — `ignore_subscribe_messages=True` 로 대부분 걸러지지만 방어.
                continue

            data = msg.get("data")
            try:
                envelope = json.loads(data) if isinstance(data, str) else json.loads(
                    data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
                )
            except (json.JSONDecodeError, TypeError, AttributeError) as e:
                logger.warning(
                    "envelope 파싱 실패 (drop): err={}", type(e).__name__,
                )
                continue

            try:
                async with worker_tick("fanout_dispatch"):
                    await fanout.dispatch_envelope(envelope)
            except Exception as e:
                # _local_* 가 자체 흡수하지만 방어적으로 한번 더 — 한 envelope 가 루프 전체를 죽이지 않게.
                logger.warning(
                    "envelope 처리 실패 (drop): op={}, err={}",
                    envelope.get("op"), type(e).__name__,
                )
    finally:
        try:
            await pubsub.unsubscribe(channel)
        except Exception as e:
            logger.warning(
                "pubsub unsubscribe 실패 (무시): {}", type(e).__name__,
            )
        try:
            await pubsub.close()
        except Exception as e:
            logger.warning(
                "pubsub close 실패 (무시): {}", type(e).__name__,
            )
        logger.info("fan-out 디스패처 종료: channel={}", channel)


async def start_fanout_dispatcher(fanout: FanoutService) -> None:
    """앱 startup 1회. `FANOUT_MODE=in_process` 면 no-op.

    `pubsub.subscribe` 를 반환 전에 await — startup race 차단 (모듈 docstring 참조).
    """
    global _dispatcher_task, _stop_event

    if settings.FANOUT_MODE != "node_channel":
        return

    if _dispatcher_task is not None and not _dispatcher_task.done():
        logger.warning("fan-out 디스패처 중복 시작 무시")
        return

    redis = await get_redis_client()
    pubsub = redis.pubsub()
    channel = node_channel_key(settings.NODE_ID)
    await pubsub.subscribe(channel)
    logger.info("fan-out 디스패처 시작: channel={}", channel)

    _stop_event = asyncio.Event()
    _dispatcher_task = asyncio.create_task(
        _dispatch_loop(pubsub, fanout, _stop_event),
        name="chat-fanout-dispatch",
    )


async def stop_fanout_dispatcher() -> None:
    """앱 shutdown — graceful 종료 후 `GRACE_SEC` 초과 시 cancel.

    `stop_node_registry` 이후에 호출 — registry 가 ZSET 에서 먼저 빠져야 다른 노드 publisher
    가 우리를 즉시 제외하고, 그 사이 in-flight envelope 까지 처리한 뒤 unsubscribe.
    """
    global _dispatcher_task, _stop_event

    task = _dispatcher_task
    event = _stop_event
    _dispatcher_task = None
    _stop_event = None

    if task is None or event is None:
        return

    event.set()
    try:
        await asyncio.wait_for(task, timeout=DISPATCHER_SHUTDOWN_GRACE_SEC)
    except asyncio.TimeoutError:
        logger.warning(
            "fan-out 디스패처가 {}s 내에 종료되지 않아 강제 취소",
            DISPATCHER_SHUTDOWN_GRACE_SEC,
        )
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    except Exception as e:
        logger.warning("fan-out 디스패처 종료 대기 중 예외: {}", e)
