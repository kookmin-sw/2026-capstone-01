import time

from app.core.instrumentation import ai_inference, ai_model_load_duration_set
from app.core.ai.papago_translator.v1.model import (
    DetectResult,
    LangCode,
    PapagoTranslatorModel,
    TranslateResult,
)


class PapagoTranslator:
    """Papago 번역기 — 자유 문장의 언어 감지 / 번역을 수행합니다."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance


    def load(self) -> None:
        """서버 시작 시 한 번 호출된다."""
        if self._initialized:
            return
        started = time.perf_counter()
        self._model = PapagoTranslatorModel()
        self._model.load_client()
        ai_model_load_duration_set("papago", time.perf_counter() - started)
        self._initialized = True


    async def close(self) -> None:
        """서버 종료 시 호출. 외부 HTTP 커넥션을 정리한다."""
        if not self._initialized:
            return
        await self._model.close_client()
        self._initialized = False


    async def detect(self, text: str) -> DetectResult:
        """언어 감지 진입점.

        Args:
            text: 감지할 원문

        Returns:
            DetectResult (lang_code)
        """
        if not self._initialized:
            raise RuntimeError("모델이 로드되지 않았습니다.")
        async with ai_inference("papago"):
            return await self._model.detect(text)


    async def translate(
        self,
        text: str,
        source: LangCode,
        target: LangCode,
    ) -> TranslateResult:
        """번역 진입점.

        Args:
            text: 번역할 원문
            source: 원문 언어 코드 (ko | en)
            target: 대상 언어 코드 (ko | en)

        Returns:
            TranslateResult (translated_text)
        """
        if not self._initialized:
            raise RuntimeError("모델이 로드되지 않았습니다.")
        async with ai_inference("papago"):
            return await self._model.translate(text, source, target)
