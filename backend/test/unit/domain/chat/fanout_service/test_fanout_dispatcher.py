"""FanoutDispatcher 단위 테스트 — startup race 차단 회귀 방지에 집중.

핵심 보장:
    `start_fanout_dispatcher` 가 반환될 때엔 이미 `pubsub.subscribe` 가 await 까지
    완료된 상태여야 한다. 이 보장이 깨지면 main.py 의 다음 라인 (`start_node_registry`)
    이 ZSET 등록을 끝낸 사이 다른 노드의 publish 가 SUBSCRIBE 전 채널에 도달해 누락.

`_dispatch_loop` 자체는 비결정적 (pubsub 폴링 루프) 이라 통합 테스트 영역에 가깝고,
여기선 진입 / 종료 / cleanup 까지의 결정적 경로만 다룬다.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
async def stub_pubsub_redis(monkeypatch):
    """`get_redis_client` 를 stub 으로 가로채 pubsub 객체 호출 순서를 캡처.

    반환: `(pubsub_mock, redis_mock)`. 테스트는 pubsub.subscribe 가 정확히 한 번
    await 되는지 + start 함수 반환 *전* 에 await 됐는지 검증 가능.

    teardown: `_dispatcher_task` 가 살아있으면 cancel + await 까지 마쳐 모듈 전역 상태가
    다음 테스트로 누수되지 않도록. async fixture 라 `gather` 가능 — `stop_fanout_dispatcher`
    를 호출하지 않은 테스트 (early-return 케이스 등) 의 안전망.
    """
    pubsub = MagicMock(name="pubsub")
    pubsub.subscribe = AsyncMock()
    # 디스패처 루프가 즉시 None 만 받게 해 cancel/stop 시 정리 빠름.
    pubsub.get_message = AsyncMock(return_value=None)
    pubsub.unsubscribe = AsyncMock()
    pubsub.close = AsyncMock()

    redis = MagicMock(name="redis")
    redis.pubsub = MagicMock(return_value=pubsub)

    async def _get_client():
        return redis
    monkeypatch.setattr(
        "app.domain.chat.worker.fanout_dispatcher.get_redis_client",
        _get_client,
    )

    from app.config import setting as setting_module
    monkeypatch.setattr(setting_module.settings, "FANOUT_MODE", "node_channel")
    monkeypatch.setattr(setting_module.settings, "NODE_ID", "test-node")

    yield pubsub, redis

    from app.domain.chat.worker import fanout_dispatcher as fd
    task = fd._dispatcher_task
    if task is not None and not task.done():
        if fd._stop_event is not None:
            fd._stop_event.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    fd._dispatcher_task = None
    fd._stop_event = None


@pytest.mark.unit
class TestStartFanoutDispatcher:
    async def test_subscribes_before_returning(self, stub_pubsub_redis):
        """반환 시점에 `pubsub.subscribe` 가 이미 await 완료여야 한다 (1번 race 회귀 방지)."""
        from app.domain.chat.worker.fanout_dispatcher import (
            start_fanout_dispatcher,
            stop_fanout_dispatcher,
        )

        pubsub, _ = stub_pubsub_redis
        fanout = MagicMock(name="fanout-stub")
        fanout.dispatch_envelope = AsyncMock()

        await start_fanout_dispatcher(fanout)

        # 함수 반환 *직후* subscribe 호출이 이미 완료 — task body 가 늦게 깨어나도
        # 무관해야 한다 (이 보장이 main.py 의 startup 순서 안정성의 근거).
        pubsub.subscribe.assert_awaited_once_with("node:test-node")

        await stop_fanout_dispatcher()

    async def test_in_process_mode_is_noop(self, monkeypatch):
        """`in_process` 모드에선 pubsub 자체를 만들지 않는다 (Redis 호출 0)."""
        from app.config import setting as setting_module
        monkeypatch.setattr(setting_module.settings, "FANOUT_MODE", "in_process")

        called = False

        async def _get_client():
            nonlocal called
            called = True
            return MagicMock()
        monkeypatch.setattr(
            "app.domain.chat.worker.fanout_dispatcher.get_redis_client",
            _get_client,
        )

        from app.domain.chat.worker.fanout_dispatcher import start_fanout_dispatcher
        fanout = MagicMock(name="fanout-stub")
        await start_fanout_dispatcher(fanout)

        assert called is False, "in_process 모드인데 Redis 클라이언트가 호출됨"

    async def test_duplicate_start_is_warned_and_skipped(self, stub_pubsub_redis):
        """이미 떠있으면 두 번째 호출은 no-op — subscribe 추가 호출 없음."""
        from app.domain.chat.worker.fanout_dispatcher import (
            start_fanout_dispatcher,
            stop_fanout_dispatcher,
        )

        pubsub, _ = stub_pubsub_redis
        fanout = MagicMock(name="fanout-stub")
        fanout.dispatch_envelope = AsyncMock()

        await start_fanout_dispatcher(fanout)
        await start_fanout_dispatcher(fanout)   # 두 번째

        assert pubsub.subscribe.await_count == 1

        await stop_fanout_dispatcher()


@pytest.mark.unit
class TestStopFanoutDispatcher:
    async def test_stop_unsubscribes_and_closes(self, stub_pubsub_redis):
        from app.domain.chat.worker.fanout_dispatcher import (
            start_fanout_dispatcher,
            stop_fanout_dispatcher,
        )

        pubsub, _ = stub_pubsub_redis
        fanout = MagicMock(name="fanout-stub")
        fanout.dispatch_envelope = AsyncMock()

        await start_fanout_dispatcher(fanout)
        await stop_fanout_dispatcher()

        pubsub.unsubscribe.assert_awaited_once()
        pubsub.close.assert_awaited_once()
