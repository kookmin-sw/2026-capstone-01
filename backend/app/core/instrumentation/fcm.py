"""FCM 멀티캐스트 / 디바이스 결과 / 토큰 정리 메트릭 헬퍼."""
import time
from contextlib import asynccontextmanager

from app.core.metric import (
    FCM_MULTICAST_DEVICES_TOTAL,
    FCM_MULTICAST_DURATION,
    FCM_SEND_TOTAL,
    FCM_TOKEN_PURGED_TOTAL,
)


# fcm_send_total result enum:
#   - ok            : multicast 호출 정상 (디바이스별 결과는 fcm_multicast_devices_total 참조)
#   - global_failed : FirebaseError (인증/네트워크 등 호출 자체 실패)
#   - other         : 그 외 예외
FCM_SEND_RESULTS = ("ok", "global_failed", "other")

# fcm_multicast_devices_total outcome enum:
#   - success             : resp.success=True
#   - failed_unregistered : UnregisteredError (토큰 무효 → bulk purge 대상)
#   - failed_other        : 그 외 디바이스별 에러
FCM_MULTICAST_OUTCOMES = ("success", "failed_unregistered", "failed_other")

# FCM multicast 호출 path enum — timer / send_inc 가 공유. 향후 marketing /
# system_notification 등 추가 시 tuple 확장 1곳만 수정.
FCM_PATHS = ("chat",)
_KNOWN_FCM_PATHS = frozenset(FCM_PATHS)


def _normalize_fcm_path(path) -> str:
    """FCM 호출 path 라벨을 화이트리스트로 정규화."""
    if isinstance(path, str) and path in _KNOWN_FCM_PATHS:
        return path
    return "other"


@asynccontextmanager
async def fcm_multicast_timer(path: str):
    """multicast 1 호출의 처리 시간만 측정. 결과 분류는 호출 측이 fcm_send_inc 로 명시.

    호출 시간은 예외 발생 시에도 finally 에서 관측되어 'global 실패까지 얼마나 걸렸나' 가 보인다.
    path 라벨은 _normalize_fcm_path 로 통과 — fcm_send_inc 와 동일 정규화 보장.
    """
    label = _normalize_fcm_path(path)
    started = time.perf_counter()
    try:
        yield
    finally:
        FCM_MULTICAST_DURATION.labels(path=label).observe(time.perf_counter() - started)


def fcm_send_inc(path: str, result: str) -> None:
    """multicast 호출 결과 카운트. result 는 FCM_SEND_RESULTS 중 하나.

    path / result 양쪽 라벨 모두 화이트리스트 통과 — 누수 차단.
    """
    path_label = _normalize_fcm_path(path)
    result_label = result if result in FCM_SEND_RESULTS else "other"
    FCM_SEND_TOTAL.labels(path=path_label, result=result_label).inc()


def fcm_multicast_devices_inc(*, success: int, failed_unregistered: int, failed_other: int) -> None:
    """multicast 의 디바이스별 결과 합산 카운트. 0 인 outcome 은 no-op."""
    if success > 0:
        FCM_MULTICAST_DEVICES_TOTAL.labels(outcome="success").inc(success)
    if failed_unregistered > 0:
        FCM_MULTICAST_DEVICES_TOTAL.labels(outcome="failed_unregistered").inc(failed_unregistered)
    if failed_other > 0:
        FCM_MULTICAST_DEVICES_TOTAL.labels(outcome="failed_other").inc(failed_other)


def fcm_token_purged_inc(count: int) -> None:
    """UnregisteredError 토큰 bulk delete 후 정리된 토큰 수만큼 카운트."""
    if count > 0:
        FCM_TOKEN_PURGED_TOTAL.inc(count)
