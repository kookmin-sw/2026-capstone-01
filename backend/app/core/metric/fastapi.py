"""FastAPI HTTP 계층 메트릭 — RED 자동 instrumentation + /health/deep canary.

prometheus_fastapi_instrumentator 가 모든 HTTP 핸들러를 자동으로 라벨링한다.
/metrics, /health, /health/deep, /ready 는 RED 에서 제외 — 모니터링 자체 트래픽 /
외부 의존성 ping 이라 사용자 트래픽 분포를 왜곡한다.

DEEP_CANARY_DURATION 은 /health/deep 의 4-store ping latency 를 따로 추적한다.
"""
from prometheus_client import Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator.metrics import (
    latency,
    request_size,
    requests,
    response_size,
)


# /health/deep 4-ping 응답 시간 히스토그램.
# 사용자 트래픽 RED 와 분리해야 외부 의존성 ping 으로 latency 분포가 왜곡되지 않는다.
# /health/deep 핸들러는 RED 에서 제외하고 이 메트릭으로만 추적한다.
DEEP_CANARY_DURATION = Histogram(
    "deep_canary_duration_seconds",
    "Latency of /health/deep four-store ping.",
    labelnames=("result",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


def build_instrumentator() -> Instrumentator:
    """prometheus-fastapi-instrumentator 를 생성한다.

    옵션:
      - should_group_untemplated=True: 무작위 path 가 handler 라벨을 폭발시키는 것을 막는다.
      - should_group_status_codes=False: 200/404/500 같은 개별 status 를 보존한다.
      - excluded_handlers: /metrics 와 /health 는 모니터링 자체 트래픽이라 제외한다.
        /health/deep 과 /ready 는 deep_canary_duration_seconds 로 따로 추적하므로 RED 에서 제외한다.

    instrument(app) 만 호출하고 expose(app) 는 호출하지 않는다.
    /metrics 는 prometheus_client.start_http_server 가 별도 포트에서 노출한다.
    """
    instrumentator = Instrumentator(
        should_group_untemplated=True,
        should_group_status_codes=False,
        excluded_handlers=[
            r"^/metrics$",
            r"^/health$",
            r"^/health/deep$",
            r"^/ready$",
        ],
    )

    # add-on 4종은 명시 등록이 필요하다.
    # 누락하면 API Overview 의 in-progress, size 패널이 침묵한다.
    instrumentator.add(
        requests(
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
        )
    )
    instrumentator.add(
        latency(
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
        )
    )
    instrumentator.add(
        request_size(should_include_handler=True, should_include_method=True)
    )
    instrumentator.add(
        response_size(should_include_handler=True, should_include_method=True)
    )

    return instrumentator
