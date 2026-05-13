"""이벤트 루프 lag / asyncio task / DB pool gauge 폴링.

1초 sleep 의 깨어남 지연을 lag 으로 관측하고 같은 tick 에서 asyncio.all_tasks() 갯수와
DB pool gauge 를 갱신한다. 트래픽 0 일 때도 pool gauge 가 stale 되지 않게 보장.
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


# main.py lifespan 이 보관할 task 핸들. shutdown 에서 cancel.
_event_loop_monitor_task = None


async def _event_loop_lag_loop() -> None:
    """1 초 sleep 한 뒤 elapsed 와의 차이를 lag 으로 관측한다.

    이벤트 루프가 다른 task 로 인해 포화 상태이면 sleep 깨어남이 지연되어 lag > 0.
    같은 tick 에서:
      - asyncio.all_tasks() 갯수 (누수 신호)
      - DB pool gauge (트래픽 0 일 때도 fresh — after_cursor_execute 의존 stale 방지)
    """
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
            # all_tasks 가 loop 정리 단계에서 RuntimeError 를 낼 수 있음 — 메트릭만 skip.
            pass

        # DB pool gauge — 트래픽 0 일 때도 1 초 주기로 갱신해 stale 방지.
        engine = _get_pool_engine()
        if engine is not None:
            try:
                pool = engine.sync_engine.pool
                DB_POOL_CHECKED_OUT.set(pool.checkedout())
                DB_POOL_SIZE.set(pool.size())
            except Exception:
                pass


def start_event_loop_monitor() -> None:
    """lifespan startup 에서 1 회 호출. 이벤트 루프 lag 측정 백그라운드 태스크 spawn."""
    global _event_loop_monitor_task

    if _event_loop_monitor_task is not None and not _event_loop_monitor_task.done():
        return
    _event_loop_monitor_task = asyncio.create_task(
        _event_loop_lag_loop(), name="krip-event-loop-monitor",
    )


async def stop_event_loop_monitor() -> None:
    """lifespan shutdown 에서 호출. cancel 후 짧게 대기.

    task 종료 확인 후 db 모듈의 pool engine reference 도 None 으로 해제 — pytest 등에서
    lifespan 을 여러 번 진입할 때 stale engine 참조가 module level 에 남아 GC 를 막거나
    다음 사이클로 leak 되는 것을 차단. attach_db_instrumentation 가 다음 호출에서 새
    engine 으로 다시 셋팅하므로 정상 동작.

    reset 시점이 await 후인 이유: cancel → await 사이 lag loop 가 마지막 iteration 을
    돌 수 있는데, 그 시점에 engine 이 None 이면 의미 없는 try/except 진입. 깨끗하게
    종료된 뒤 reset 하는 게 자연스럽다.
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
