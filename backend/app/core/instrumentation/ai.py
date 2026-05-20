"""AI inference / 외부 provider 호출 / 토큰 사용량 메트릭.

LLMManager 의 Gemini 콜백, 도메인 inference 컨텍스트, papago/gemini 외부 호출 측정을 모은다.
"""
from typing import Any
import time
from langchain_core.outputs import LLMResult
from langchain_core.callbacks import BaseCallbackHandler
from contextlib import asynccontextmanager
from collections import OrderedDict

from app.core.metric import (
    AI_EXTERNAL_CALL_DURATION,
    AI_EXTERNAL_CALL_TOTAL,
    AI_INFERENCE_DURATION,
    AI_INFERENCE_TOTAL,
    AI_MODEL_LOAD_DURATION,
    AI_TOKEN_USAGE_TOTAL,
)


# AI 서비스 식별자 (도메인 측).
AI_MODEL_NAMES = ("menu_ocr", "papago", "tour_planner")

AI_RESULTS = ("ok", "error", "other")

_KNOWN_AI_PROVIDERS = frozenset({"gemini", "papago"})
AI_PROVIDERS = ("gemini", "papago")


def _normalize_ai_provider(provider) -> str:
    if isinstance(provider, str) and provider in _KNOWN_AI_PROVIDERS:
        return provider
    return "other"


# 주의: 이 라벨은 AI 서비스 식별자 (`menu_ocr` 등). `ai_token_usage_inc` 의 `model` 라벨
# (실제 LLM 모델 id) 과 의미가 다르다.
_KNOWN_AI_MODEL_NAMES = frozenset(AI_MODEL_NAMES)


def _normalize_ai_model_service(model) -> str:
    if isinstance(model, str) and model in _KNOWN_AI_MODEL_NAMES:
        return model
    return "other"


def ai_model_load_duration_set(model: str, duration_seconds: float) -> None:
    """startup 직후 1회. load() 종료 시각의 duration 을 set."""
    AI_MODEL_LOAD_DURATION.labels(model=_normalize_ai_model_service(model)).set(duration_seconds)


@asynccontextmanager
async def ai_inference(model: str):
    """AI inference 1 호출 wrap — result 자동 분류 + duration + raise 보존."""
    label = _normalize_ai_model_service(model)
    started = time.perf_counter()
    result = "ok"
    try:
        yield
    except Exception:
        result = "error"
        raise
    finally:
        elapsed = time.perf_counter() - started
        AI_INFERENCE_TOTAL.labels(model=label, result=result).inc()
        AI_INFERENCE_DURATION.labels(model=label).observe(elapsed)


@asynccontextmanager
async def ai_external_call(provider: str):
    """외부 AI provider 호출 1건 wrap."""
    label = _normalize_ai_provider(provider)
    started = time.perf_counter()
    result = "ok"
    try:
        yield
    except Exception:
        result = "error"
        raise
    finally:
        elapsed = time.perf_counter() - started
        AI_EXTERNAL_CALL_TOTAL.labels(provider=label, result=result).inc()
        AI_EXTERNAL_CALL_DURATION.labels(provider=label).observe(elapsed)


def ai_token_usage_inc(provider: str, model: str, *, input_tokens: int = 0, output_tokens: int = 0) -> None:
    """LLM 응답 usage_metadata 토큰 수 카운트.

    `model` 은 실제 LLM 모델 id (예: gemini-2.5-flash) — Flash↔Pro 비용 분리.
    """
    if input_tokens > 0:
        AI_TOKEN_USAGE_TOTAL.labels(provider=provider, model=model, kind="input").inc(input_tokens)
    if output_tokens > 0:
        AI_TOKEN_USAGE_TOTAL.labels(provider=provider, model=model, kind="output").inc(output_tokens)


class GeminiInstrumentationHandler(BaseCallbackHandler):
    """LangChain Gemini 호출에 external_call duration / result / token_usage 자동 부착.

    LLMManager.initialize 에서 ChatGoogleGenerativeAI 생성 시 callbacks 인자로 1회 등록.
    Tour Planner LangGraph multi-turn / menu_ocr / 향후 체인 모두 자동 적용.

    `_start_times` orphan leak 가드: on_llm_start 후 on_llm_end/error 가 모두 누락된
    run_id 가 영구 잔존할 수 있어 OrderedDict + `_MAX_INFLIGHT` cap 으로 LRU 제거.
    정상 in-flight (~수십) 은 cap 안. cap 초과 호출은 metric loss 만, 비즈 영향 0.

    토큰 추출: generations[i][0].message.usage_metadata 의 input/output_tokens.
    model 이름은 message.response_metadata 또는 llm_output, 부재 시 'unknown' fallback.
    """

    # 정상 동시 호출 ~수십의 ~20배 여유. orphan 누수 가드.
    _MAX_INFLIGHT = 1024

    def __init__(self) -> None:
        self._start_times: OrderedDict[str, float] = OrderedDict()


    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id,
        **kwargs: Any,
    ) -> None:
        self._start_times[str(run_id)] = time.perf_counter()
        if len(self._start_times) > self._MAX_INFLIGHT:
            self._start_times.popitem(last=False)


    def on_llm_end(self, response: LLMResult, *, run_id, **kwargs: Any) -> None:
        elapsed = self._stop_timer(str(run_id))
        if elapsed is not None:
            AI_EXTERNAL_CALL_DURATION.labels(provider="gemini").observe(elapsed)
        AI_EXTERNAL_CALL_TOTAL.labels(provider="gemini", result="ok").inc()
        self._record_token_usage(response)


    def on_llm_error(self, error: BaseException, *, run_id, **kwargs: Any) -> None:
        elapsed = self._stop_timer(str(run_id))
        if elapsed is not None:
            AI_EXTERNAL_CALL_DURATION.labels(provider="gemini").observe(elapsed)
        AI_EXTERNAL_CALL_TOTAL.labels(provider="gemini", result="error").inc()


    def _stop_timer(self, run_id: str) -> float | None:
        started = self._start_times.pop(run_id, None)
        if started is None:
            return None
        return time.perf_counter() - started


    @staticmethod
    def _record_token_usage(response: LLMResult) -> None:
        """추출 실패는 silent — 메트릭만 누락, 비즈 응답은 정상."""
        input_tokens = 0
        output_tokens = 0
        model_name: str | None = None

        try:
            for gen_list in response.generations:
                for gen in gen_list:
                    message = getattr(gen, "message", None)
                    if message is None:
                        continue
                    usage = getattr(message, "usage_metadata", None)
                    if isinstance(usage, dict):
                        input_tokens += int(usage.get("input_tokens", 0) or 0)
                        output_tokens += int(usage.get("output_tokens", 0) or 0)
                    if model_name is None:
                        meta = getattr(message, "response_metadata", None)
                        if isinstance(meta, dict):
                            model_name = meta.get("model_name") or meta.get("model")

            if model_name is None and response.llm_output:
                model_name = (
                    response.llm_output.get("model_name")
                    or response.llm_output.get("model")
                )

            if model_name is None:
                model_name = "unknown"

            ai_token_usage_inc(
                "gemini",
                model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        except Exception:
            pass
