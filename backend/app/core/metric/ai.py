"""AI 도메인 메트릭 — 모델 load / inference / 외부 provider 호출 / token usage.

`model` 라벨의 의미가 메트릭별로 다르다 (description 참조):
  - LOAD / INFERENCE: 서비스 식별자 (menu_ocr | papago | tour_planner)
  - TOKEN_USAGE: 실제 LLM 모델 id (gemini-2.5-flash 등) — Flash↔Pro 비용 분리용
"""
from prometheus_client import Counter, Gauge, Histogram


AI_MODEL_LOAD_DURATION = Gauge(
    "ai_model_load_duration_seconds",
    "AI model load() duration set once at startup. model: service identifier.",
    labelnames=("model",),
)

AI_INFERENCE_TOTAL = Counter(
    "ai_inference_total",
    "AI inference invocation count. model: service identifier (menu_ocr|papago|tour_planner).",
    labelnames=("model", "result"),
)

AI_INFERENCE_DURATION = Histogram(
    "ai_inference_duration_seconds",
    "AI inference invocation duration. model: service identifier.",
    labelnames=("model",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

AI_EXTERNAL_CALL_TOTAL = Counter(
    "ai_external_call_total",
    "External AI provider call count. provider: gemini|papago.",
    labelnames=("provider", "result"),
)

AI_EXTERNAL_CALL_DURATION = Histogram(
    "ai_external_call_duration_seconds",
    "External AI provider call duration.",
    labelnames=("provider",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

AI_TOKEN_USAGE_TOTAL = Counter(
    "ai_token_usage_total",
    "LLM token consumption. model label is the actual LLM model id (e.g., gemini-2.5-flash).",
    labelnames=("provider", "model", "kind"),
)
