"""FCM multicast 호출 / 디바이스 outcome / 토큰 정리 메트릭.

multicast 1 건 = send_chat_push 1 호출. 디바이스 outcome 은 별도 메트릭으로 분리한다.
"""
from prometheus_client import Counter, Histogram


FCM_SEND_TOTAL = Counter(
    "fcm_send_total",
    "FCM multicast send invocation count by path and result.",
    labelnames=("path", "result"),
)

FCM_MULTICAST_DEVICES_TOTAL = Counter(
    "fcm_multicast_devices_total",
    "Per-device delivery outcome inside one multicast call.",
    labelnames=("outcome",),
)

FCM_MULTICAST_DURATION = Histogram(
    "fcm_multicast_duration_seconds",
    "FCM multicast call duration (asyncio.to_thread + Firebase round-trip).",
    labelnames=("path",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

FCM_TOKEN_PURGED_TOTAL = Counter(
    "fcm_token_purged_total",
    "FCM token rows deleted due to UnregisteredError responses.",
)
