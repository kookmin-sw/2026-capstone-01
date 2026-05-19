"""채팅 fan-out Pub/Sub 디스패처.

`FANOUT_MODE=node_channel` 모드에서 lifespan startup 시 1 회 시작. `node:{NODE_ID}`
채널을 SUBSCRIBE 해 envelope 을 받으며, `FanoutService.dispatch_envelope` 으로 라우팅.

ordering 보장:
    Redis 는 동일 채널 내 메시지를 publish 순서대로 전달. 디스패처는 이 보장을 깨지 않기
    위해 **직렬 처리** — 한 메시지 처리가 길어지면 후속이 지연되지만, `_local_*` 는 메모리
    dict + `gather` 기반 WS send 라 일반적으로 ms 단위.

    invite/leave 의 "subscribe → fan_out_to_user → send_system_message" 순서가 동일
    publisher → 동일 채널이면 보존 (room.py 의 race 차단 의도 그대로 유지).

startup 순서 race 차단:
    `start_fanout_dispatcher` 는 `pubsub.subscribe` 가 **확정된 뒤** 반환한다. main.py
    가 그 다음에 `start_node_registry` 로 ZSET 에 자기 노드를 등록하므로, 다른 노드가
    `list_active_nodes` 로 우리를 인지하는 시점엔 이미 채널이 활성. 반대 순서면 다른
    노드의 publish 가 SUBSCRIBE 전에 도달해 누락.

`main.py` lifespan 에서 `start_fanout_dispatcher(fanout_service)` 1 회 호출,
shutdown 시 `stop_fanout_dispatcher()` 호출. 패턴은 `chat.worker.reconcile` 과 동일.
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


# ──────────────────── 튜닝 상수 ────────────────────

# `pubsub.get_message` 폴링 간격 — 짧으면 stop_event 반응성 좋고, 길면 idle CPU 절감.
# 1.0s 면 shutdown 시 최대 1초 지연 정도라 acceptable.
DISPATCHER_POLL_TIMEOUT_SEC = 1.0

# pubsub 자체 장애로 get_message 가 연속 실패할 때의 backoff. 너무 짧으면 로그 폭주.
DISPATCHER_ERROR_BACKOFF_SEC = 1.0

# shutdown 시 루프가 stop_event 감지 후 unsubscribe 까지 마치는 데 줄 최대 유예.
DISPATCHER_SHUTDOWN_GRACE_SEC = 5.0


# ──────────────────── 모듈 상태 ────────────────────

_dispatcher_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


# ──────────────────── 핵심 로직 ────────────────────

async def _dispatch_loop(
    pubsub,
    fanout: FanoutService,
    stop_event: asyncio.Event,
) -> None:
    """이미 SUBSCRIBE 된 pubsub 으로 envelope 직렬 처리.

    pubsub 자체 장애 (Redis 재시작 등) 시 backoff 후 재시도 — 본 함수가 cancel 되기 전엔
    절대 종료되지 않도록 모든 예외를 안에서 흡수한다. 종료는 `stop_event` set + while
    조건 재평가가 단일 진입점 — break 분기 두지 않아 흐름 단순화.
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
                # backoff 동안 stop 신호가 오면 wait_for 가 즉시 깨어남. 깨어나든
                # 타임아웃이든 결과는 무시하고 while 조건이 종료 여부를 결정 — 단일 책임.
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=DISPATCHER_ERROR_BACKOFF_SEC,
                    )
                except asyncio.TimeoutError:
                    pass
                continue

            # liveness 신호 — envelope 0 건이어도 polling 살아있는 한 last_tick 갱신.
            # WorkerStale 알람의 false positive 차단.
            chat_fanout_dispatch_alive()

            if msg is None:
                continue
            if msg.get("type") != "message":
                # subscribe ACK 등 (`ignore_subscribe_messages=True` 로 대부분 걸러지지만 방어).
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
                # _local_* 는 자체 예외를 흡수하지만 방어적으로 한번 더 — 한 envelope 실패가
                # 디스패처 루프 전체를 죽이지 않도록.
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


# ──────────────────── 스케줄러 훅 ────────────────────

async def start_fanout_dispatcher(fanout: FanoutService) -> None:
    """앱 startup 에서 1 회 호출. `FANOUT_MODE=in_process` 면 no-op.

    `pubsub.subscribe` 를 **함수 반환 전에 await** 한다 — startup race 차단 핵심.
    `create_task` 만 하고 반환하면 task 가 스케줄링되어 subscribe 가 실행되기 전에
    `start_node_registry()` 가 ZSET 등록을 끝내고, 그 사이 다른 노드의 publish 가 우리
    채널에 도달해 SUBSCRIBE 전이라 누락된다. main.py 가 본 함수를 await 한 직후 registry
    를 등록하므로 함수 반환 시점에 채널 활성이 보장돼야 함.
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
    """앱 shutdown 에서 호출. 루프를 graceful 종료하되 `GRACE_SEC` 초과 시 cancel.

    `stop_node_registry` **이후** 에 호출 — registry 가 ZSET 에서 먼저 빠져야 다른 노드의
    publisher 가 다음 `list_active_nodes` 호출부터 우리를 즉시 제외하고, 그 동안 in-flight
    envelope 까지 디스패처가 처리한 뒤 unsubscribe (main.py shutdown 순서가 이를 강제).
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
