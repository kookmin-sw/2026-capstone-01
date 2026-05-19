"""AI inference / 외부 provider 호출 / 토큰 사용량 메트릭.

LLMManager 의 Gemini callbacks 와 도메인의 inference 컨텍스트 매니저, 외부 provider
호출 (papago / gemini) 측정을 한 곳에 둔다.
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


# AI 서비스 식별자.
AI_MODEL_NAMES = ("menu_ocr", "papago", "tour_planner")

# inference / external_call result enum:
#   - ok    : 정상 종료
#   - error : 예외 발생 (호출 측이 swallow 또는 propagate 자유)
#   - other : 향후 분류 추가 시 catch-all (현재 코드는 발생 시점 없음)
AI_RESULTS = ("ok", "error", "other")

# 외부 AI provider 화이트리스트. 호출자가 raw 문자열 보내도 'other' 로 통합.
_KNOWN_AI_PROVIDERS = frozenset({"gemini", "papago"})

# 외부 AI provider 식별자 (외부 노출용 enum).
AI_PROVIDERS = ("gemini", "papago")


def _normalize_ai_provider(provider) -> str:
    """provider 라벨을 화이트리스트로 정규화 — 향후 호출 지점 추가 시 안전."""
    if isinstance(provider, str) and provider in _KNOWN_AI_PROVIDERS:
        return provider
    return "other"


# AI 서비스 식별자 (load + inference 공유). AI_MODEL_NAMES tuple 의 frozenset 미러.
# `ai_token_usage_inc` 의 model 라벨과는 의미가 다르다 (그쪽은 실제 LLM 모델 id).
_KNOWN_AI_MODEL_NAMES = frozenset(AI_MODEL_NAMES)


def _normalize_ai_model_service(model) -> str:
    """AI 서비스 식별자 라벨을 화이트리스트로 정규화 — AI_MODEL_NAMES 미반영 호출 보호."""
    if isinstance(model, str) and model in _KNOWN_AI_MODEL_NAMES:
        return model
    return "other"


def ai_model_load_duration_set(model: str, duration_seconds: float) -> None:
    """startup 직후 1 회만 호출. load() 종료 시점에 측정한 시간을 set."""
    AI_MODEL_LOAD_DURATION.labels(model=_normalize_ai_model_service(model)).set(duration_seconds)


@asynccontextmanager
async def ai_inference(model: str):
    """AI inference 1 호출 wrap. result 자동 분류 + duration 관측 + raise 보존.

    model 라벨은 _normalize_ai_model_service 로 화이트리스트 통과 — AI_MODEL_NAMES 미반영
    호출이 들어와도 'other' 로 통합되어 카디널리티 누수 차단.
    """
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
    """외부 AI provider 호출 1건 wrap. provider 라벨은 화이트리스트로 정규화 — 카디널리티 보호."""
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
    """LLM 응답의 usage_metadata 에서 추출한 토큰 수를 카운트.

    model 라벨은 실제 LLM 모델 id (예: gemini-2.5-flash) — Flash↔Pro 비용 분리 핵심.
    """
    if input_tokens > 0:
        AI_TOKEN_USAGE_TOTAL.labels(provider=provider, model=model, kind="input").inc(input_tokens)
    if output_tokens > 0:
        AI_TOKEN_USAGE_TOTAL.labels(provider=provider, model=model, kind="output").inc(output_tokens)


class GeminiInstrumentationHandler(BaseCallbackHandler):
    """LangChain Gemini 호출에 external_call duration / result 와 token_usage 메트릭을 자동 부착.

    LLMManager.initialize 에서 ChatGoogleGenerativeAI 생성 시 callbacks 인자로 1 회 등록한다.
    Tour Planner 의 LangGraph multi-turn 호출과 menu_ocr / 향후 추가 체인 모두 자동 적용.

    동작:
      - on_llm_start: run_id 별 시작 시각 보관 (concurrent multi-turn 안전)
      - on_llm_end:   duration 관측 + result=ok 카운트 + token_usage 추출
      - on_llm_error: duration 관측 + result=error 카운트

    메모리 가드:
      `_start_times` 는 on_llm_start 가 fire 됐는데 on_llm_end / on_llm_error 가 모두 누락된
      orphan run_id 가 영구 잔존하는 경로가 있다 (LangChain 내부 예외, 콜백 chain 단절 등).
      장시간 운영 시 미미하나 누적 leak 이라, OrderedDict + `_MAX_INFLIGHT` cap 으로 LRU
      (insertion-order) 제거. 정상 in-flight 호출 (~수십 건) 은 cap 안에 들어오므로 측정
      누락 없음. cap 보다 오래 걸리는 호출은 매우 드물고 metric loss 만 발생, 비즈 영향 0.

    토큰 추출:
      langchain_google_genai 의 응답은 generations[i][0].message.usage_metadata 에
      {"input_tokens", "output_tokens", ...} 를 노출. model 이름은 message.response_metadata
      또는 llm_output 에서. 둘 다 부재 시 'unknown' 으로 fallback (메트릭은 누락 없이 들어감).
    """

    # in-flight run_id 보관 cap. orphan 누수 가드 — 정상 동시 호출 (~수십) 의 ~20배 여유.
    # 1025 번째 진입 시 가장 오래된 entry 제거 → 정확히 1024 cap 유지 (`>` 비교).
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
            # 가장 오래된 insertion 제거 — orphan run_id 누수 차단.
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
        """추출 실패는 silent — 메트릭만 누락, 비즈는 정상 응답."""
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
