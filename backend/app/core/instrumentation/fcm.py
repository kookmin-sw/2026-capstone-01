"""FCM 멀티캐스트 / 디바이스 결과 / 토큰 정리 메트릭."""
import time
from contextlib import asynccontextmanager

from app.core.metric import (
    FCM_MULTICAST_DEVICES_TOTAL,
    FCM_MULTICAST_DURATION,
    FCM_SEND_TOTAL,
    FCM_TOKEN_PURGED_TOTAL,
)


# fcm_send_total result:
# - ok            : multicast 호출 정상 (디바이스별은 fcm_multicast_devices_total)
# - global_failed : FirebaseError (인증/네트워크 등 호출 자체 실패)
# - other         : 그 외
FCM_SEND_RESULTS = ("ok", "global_failed", "other")

# fcm_multicast_devices_total outcome:
# - success             : resp.success=True
# - failed_unregistered : UnregisteredError (토큰 무효 → bulk purge 대상)
# - failed_other        : 그 외 디바이스 에러
FCM_MULTICAST_OUTCOMES = ("success", "failed_unregistered", "failed_other")

# 향후 marketing / system_notification 등 추가 시 여기만 확장.
FCM_PATHS = ("chat",)
_KNOWN_FCM_PATHS = frozenset(FCM_PATHS)


def _normalize_fcm_path(path) -> str:
    if isinstance(path, str) and path in _KNOWN_FCM_PATHS:
        return path
    return "other"


@asynccontextmanager
async def fcm_multicast_timer(path: str):
    """multicast 1 호출의 처리 시간. 결과 분류는 호출측이 `fcm_send_inc` 로 명시.

    예외 시에도 finally 에서 관측 — global 실패까지 걸린 시간 보존.
    """
    label = _normalize_fcm_path(path)
    started = time.perf_counter()
    try:
        yield
    finally:
        FCM_MULTICAST_DURATION.labels(path=label).observe(time.perf_counter() - started)


def fcm_send_inc(path: str, result: str) -> None:
    """multicast 결과 카운트. 라벨은 화이트리스트로 통과."""
    path_label = _normalize_fcm_path(path)
    result_label = result if result in FCM_SEND_RESULTS else "other"
    FCM_SEND_TOTAL.labels(path=path_label, result=result_label).inc()


def fcm_multicast_devices_inc(*, success: int, failed_unregistered: int, failed_other: int) -> None:
    """디바이스별 결과 합산. 0 outcome 은 no-op."""
    if success > 0:
        FCM_MULTICAST_DEVICES_TOTAL.labels(outcome="success").inc(success)
    if failed_unregistered > 0:
        FCM_MULTICAST_DEVICES_TOTAL.labels(outcome="failed_unregistered").inc(failed_unregistered)
    if failed_other > 0:
        FCM_MULTICAST_DEVICES_TOTAL.labels(outcome="failed_other").inc(failed_other)


def fcm_token_purged_inc(count: int) -> None:
    """UnregisteredError 토큰 bulk delete 후 정리된 수만큼 카운트."""
    if count > 0:
        FCM_TOKEN_PURGED_TOTAL.inc(count)
