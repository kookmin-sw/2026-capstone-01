"""이벤트 루프 lag / asyncio task / DB pool gauge 폴링.

1초 sleep 의 깨어남 지연을 lag 으로 관측. 같은 tick 에서 asyncio.all_tasks 수와 pool gauge 도 갱신
— 트래픽 0 일 때도 stale 되지 않게 보장.
"""
import time
import asyncio

from app.core.metric import (
    DB_POOL_CHECKED_OUT,
    DB_POOL_SIZE,
    PYTHON_ASYNCIO_TASKS,
    PYTHON_EVENT_LOOP_LAG,
)
from app.core.instrumentation.db import _get_pool_engine, _reset_pool_engine


_event_loop_monitor_task = None


async def _event_loop_lag_loop() -> None:
    """매 1초 sleep 후 elapsed-1.0 을 lag 으로 관측. task 수 / pool gauge 도 동시 갱신."""
    while True:
        started = time.monotonic()
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        elapsed = time.monotonic() - started
        lag = max(0.0, elapsed - 1.0)
        PYTHON_EVENT_LOOP_LAG.observe(lag)
        try:
            PYTHON_ASYNCIO_TASKS.set(len(asyncio.all_tasks()))
        except RuntimeError:
            # loop 정리 단계에서 RuntimeError 가능 — 메트릭만 skip.
            pass

        engine = _get_pool_engine()
        if engine is not None:
            try:
                pool = engine.sync_engine.pool
                DB_POOL_CHECKED_OUT.set(pool.checkedout())
                DB_POOL_SIZE.set(pool.size())
            except Exception:
                pass


def start_event_loop_monitor() -> None:
    """lifespan startup 1회 — lag 측정 백그라운드 spawn."""
    global _event_loop_monitor_task

    if _event_loop_monitor_task is not None and not _event_loop_monitor_task.done():
        return
    _event_loop_monitor_task = asyncio.create_task(
        _event_loop_lag_loop(), name="krip-event-loop-monitor",
    )


async def stop_event_loop_monitor() -> None:
    """lifespan shutdown — cancel 후 짧게 대기 + pool engine 참조 해제.

    pool engine reset 은 await 종료 후 수행 — cancel/await 사이 마지막 iteration 이 engine 을
    참조할 수 있어 깨끗하게 끝난 뒤 reset.
    """
    global _event_loop_monitor_task

    task = _event_loop_monitor_task
    _event_loop_monitor_task = None
    if task is not None:
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        except Exception:
            pass
    _reset_pool_engine()
