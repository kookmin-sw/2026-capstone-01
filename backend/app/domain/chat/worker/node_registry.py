"""채팅 노드 레지스트리.

`FANOUT_MODE=node_channel` 모드에서 활성 노드 목록을 추적한다. publisher 는 fan-out 시
이 레지스트리를 조회해 모든 노드의 `node:{node_id}` 채널에 broadcast.

키 구조:
    chat:nodes   ZSET   score=만료시각ms, member=node_id

자가 치유:
    - heartbeat 으로 만료시각을 주기 갱신 (`SESSION_TTL` 과 동일한 30s 주기)
    - 크래시한 노드는 heartbeat 누락 → `list_active_nodes` 의 `ZREMRANGEBYSCORE` 로 자연 제거
    - 빈 publish 는 Redis 가 그냥 0 명 수신으로 처리하므로 stale 항목이 잠깐 남아도 안전

`main.py` lifespan 에서 `start_node_registry()` 1 회 호출, shutdown 시 `stop_node_registry()`.
패턴은 `chat.worker.reconcile` 과 동일.
"""
from __future__ import annotations
from typing import Optional
import time
import asyncio

from app.config.setting import settings
from app.core.chat.redis_key import NODE_TTL, NODES_ZSET_KEY
from app.core.instrumentation import (
    chat_active_nodes_set,
    chat_node_heartbeat_failure,
    worker_tick,
)
from app.core.logger import get_logger
from app.core.redis import get_redis_client


logger = get_logger("chat.node_registry")


# ──────────────────── 튜닝 상수 ────────────────────

# heartbeat 주기 — TTL 의 1/3 (SessionService 패턴과 동일).
NODE_HEARTBEAT_INTERVAL_SEC = NODE_TTL // 3

# shutdown 시 heartbeat 루프가 stop_event 감지 후 마치는 데 줄 최대 유예.
NODE_REGISTRY_SHUTDOWN_GRACE_SEC = 3.0


# ──────────────────── 모듈 상태 ────────────────────

_heartbeat_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


# ──────────────────── 핵심 로직 ────────────────────

def _now_ms() -> int:
    return int(time.time() * 1000)


def _expires_ms() -> int:
    return _now_ms() + NODE_TTL * 1000


async def register_self() -> None:
    """자기 노드를 ZSET 에 등록. 시작 시 1회 호출."""
    redis = await get_redis_client()
    await redis.zadd(NODES_ZSET_KEY, {settings.NODE_ID: _expires_ms()})


async def heartbeat_self() -> None:
    """자기 노드 만료시각 갱신.

    `XX` 로 이미 있는 멤버만 갱신 — deregister 직후 racy heartbeat 으로 부활하는 것을 방지
    (shutdown 시 deregister → 마지막 heartbeat 잔존 가능).
    """
    redis = await get_redis_client()
    await redis.zadd(
        NODES_ZSET_KEY, {settings.NODE_ID: _expires_ms()}, xx=True,
    )


async def deregister_self() -> None:
    """자기 노드를 ZSET 에서 제거. 종료 시 1회 호출."""
    redis = await get_redis_client()
    await redis.zrem(NODES_ZSET_KEY, settings.NODE_ID)


async def list_active_nodes() -> list[str]:
    """활성 노드 목록. 만료 항목 청소 + 조회를 1 RTT pipeline 으로.

    publisher (`FanoutService._publish_broadcast`) 가 broadcast 대상 결정에 사용.
    빈 리스트면 활성 노드 없음 — 호출측에서 publish skip.
    """
    redis = await get_redis_client()
    pipe = redis.pipeline(transaction=False)
    pipe.zremrangebyscore(NODES_ZSET_KEY, "-inf", _now_ms())
    pipe.zrange(NODES_ZSET_KEY, 0, -1)
    _, members = await pipe.execute()
    return list(members)


# ──────────────────── 주기 루프 ────────────────────

async def _heartbeat_loop(stop_event: asyncio.Event) -> None:
    """`NODE_HEARTBEAT_INTERVAL_SEC` 마다 자기 노드 만료시각 갱신.

    실패해도 로그만 남기고 계속 — 다음 tick 에 복구 가능. heartbeat 누락이 누적되어
    `NODE_TTL` 초과되면 `list_active_nodes` 가 자기 노드를 dead 로 간주하므로
    publisher 가 자기 자신에게도 publish 하지 않게 됨 (사실상 self-healing 격리).
    """
    logger.info(
        "node heartbeat 루프 시작: node_id={}, interval={}s",
        settings.NODE_ID, NODE_HEARTBEAT_INTERVAL_SEC,
    )
    while not stop_event.is_set():
        try:
            async with worker_tick("node_heartbeat"):
                await heartbeat_self()
                # heartbeat 후 활성 노드 수 갱신 — list_active_nodes 가 만료 항목을 청소하므로
                # ZSET 의 fresh 한 size 가 그대로 메트릭에 반영된다.
                chat_active_nodes_set(len(await list_active_nodes()))
        except Exception as e:
            chat_node_heartbeat_failure()
            logger.warning(
                "node heartbeat 실패 (계속 진행): node_id={}, err={}",
                settings.NODE_ID, type(e).__name__,
            )
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=NODE_HEARTBEAT_INTERVAL_SEC,
            )
            break
        except asyncio.TimeoutError:
            pass

    logger.info("node heartbeat 루프 종료: node_id={}", settings.NODE_ID)


# ──────────────────── 스케줄러 훅 ────────────────────

async def start_node_registry() -> None:
    """앱 startup 에서 1 회 호출. `FANOUT_MODE=in_process` 면 no-op.

    1) 자기 노드 등록 — list_active_nodes 호출이 시작되기 전에 완료
    2) heartbeat 루프 spawn
    """
    global _heartbeat_task, _stop_event

    if settings.FANOUT_MODE != "node_channel":
        return

    if _heartbeat_task is not None and not _heartbeat_task.done():
        logger.warning("node registry 중복 시작 무시")
        return

    await register_self()

    _stop_event = asyncio.Event()
    _heartbeat_task = asyncio.create_task(
        _heartbeat_loop(_stop_event), name="chat-node-heartbeat",
    )
    logger.info("node registry 시작: node_id={}", settings.NODE_ID)


async def stop_node_registry() -> None:
    """앱 shutdown 에서 호출. heartbeat 루프 graceful 종료 + ZSET 에서 자기 노드 제거.

    deregister 가 실패해도 stale 멤버는 `NODE_TTL` 후 자연 청소되므로 fail-open.
    """
    global _heartbeat_task, _stop_event

    task = _heartbeat_task
    event = _stop_event
    _heartbeat_task = None
    _stop_event = None

    if event is not None:
        event.set()
    if task is not None:
        try:
            await asyncio.wait_for(task, timeout=NODE_REGISTRY_SHUTDOWN_GRACE_SEC)
        except asyncio.TimeoutError:
            logger.warning(
                "node heartbeat 루프가 {}s 내에 종료되지 않아 강제 취소",
                NODE_REGISTRY_SHUTDOWN_GRACE_SEC,
            )
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        except Exception as e:
            logger.warning("node heartbeat 종료 대기 중 예외: {}", e)

    try:
        await deregister_self()
    except Exception as e:
        logger.warning(
            "node deregister 실패 (TTL 만료 대기로 fallback): node_id={}, err={}",
            settings.NODE_ID, type(e).__name__,
        )
