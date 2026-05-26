from httpx import HTTPStatusError, RequestError

from app.domain.translation.service.exception import (
    TranslationUnreachableError,
    TranslationVendorError,
)
from app.domain.translation.schema.translation import LangCode
from app.domain.translation.dto.translation import DetectData, TranslateData
from app.core.ai.papago_translator.load import PapagoTranslator


class TranslationService:
    """번역 도메인 서비스 — 현재 구현체는 Papago. 추후 vendor 교체 시 이 안만 바꾸면 된다.

    vendor SDK (httpx 등) 의 예외는 여기서 도메인 예외로 변환해 던진다.
    Router 는 도메인 예외만 알면 되므로 vendor 교체 영향이 service 안에 갇힌다.
    """

    def __init__(self):
        self._translator = PapagoTranslator()

    # ──────────────────── 언어 감지 ────────────────────

    async def detect(self, text: str) -> DetectData:
        """입력 문장의 언어를 감지합니다."""
        try:
            result = await self._translator.detect(text)
        except HTTPStatusError as e:
            raise TranslationVendorError(e.response.status_code, e.response.text) from e
        except RequestError as e:
            raise TranslationUnreachableError(str(e)) from e
        return DetectData(lang_code=result.lang_code)

    # ──────────────────── 번역 ────────────────────

    async def translate(
        self,
        text: str,
        source: LangCode,
        target: LangCode,
    ) -> TranslateData:
        """source -> target 으로 문장을 번역합니다."""
        try:
            result = await self._translator.translate(text, source, target)
        except HTTPStatusError as e:
            raise TranslationVendorError(e.response.status_code, e.response.text) from e
        except RequestError as e:
            raise TranslationUnreachableError(str(e)) from e
        return TranslateData(translated_text=result.translated_text)
