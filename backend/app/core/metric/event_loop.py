"""이벤트 루프 / asyncio 누수 보조 메트릭."""
from prometheus_client import Gauge, Histogram


PYTHON_EVENT_LOOP_LAG = Histogram(
    "python_event_loop_lag_seconds",
    "asyncio.sleep(1) 와 실제 elapsed 의 차이. 이벤트 루프 포화 신호.",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0),
)

PYTHON_ASYNCIO_TASKS = Gauge(
    "python_asyncio_tasks",
    "len(asyncio.all_tasks()) 스냅샷. 누수 (recover unread / fanout dispatch 등) 보조 신호.",
)
