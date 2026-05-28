from typing import Literal
from pydantic import BaseModel, Field
import httpx

from app.core.logger import get_logger
from app.core.instrumentation import ai_external_call
from app.config.setting import settings


logger = get_logger("papago_translator")

LangCode = Literal["ko", "en"]

DETECT_URL = "https://papago.apigw.ntruss.com/langs/v1/dect"
TRANSLATE_URL = "https://papago.apigw.ntruss.com/nmt/v1/translation"

REQUEST_TIMEOUT = 10.0


class DetectResult(BaseModel):
    """언어 감지 결과"""
    lang_code: str = Field(description="감지된 언어 코드 (예: ko, en)")


class TranslateResult(BaseModel):
    """번역 결과"""
    translated_text: str = Field(description="번역된 문장")


class PapagoTranslatorModel:
    """Papago 번역 모델 — 자유 문장의 언어 감지 / 번역을 수행합니다.

    Naver Cloud Platform (NCP) Papago API 를 백엔드에서 프록시 호출하는 방식.
    Client Secret 을 프론트에 노출하지 않기 위함.
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ):
        self._client_id = client_id or settings.PAPAGO_CLIENT_ID
        self._client_secret = client_secret or settings.PAPAGO_CLIENT_SECRET
        self._client: httpx.AsyncClient | None = None


    def load_client(self) -> None:
        """공용 비동기 HTTP 클라이언트를 메모리에 보관합니다.

        커넥션 풀 재사용으로 매 요청마다 TLS handshake 비용을 피하기 위함.
        """
        if self._client is not None:
            return

        self._client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            headers={
                "X-NCP-APIGW-API-KEY-ID": self._client_id,
                "X-NCP-APIGW-API-KEY": self._client_secret,
            },
        )
        logger.info("Papago HTTP 클라이언트 초기화 완료")


    async def close_client(self) -> None:
        """서버 종료 시 호출. 열려있는 커넥션을 정리합니다."""
        if self._client is None:
            return
        await self._client.aclose()
        self._client = None


    async def detect(self, text: str) -> DetectResult:
        """입력 문장의 언어를 감지합니다.

        Args:
            text: 언어를 감지할 원문

        Returns:
            DetectResult: lang_code (ko, en, ...)
        """
        async with ai_external_call("papago"):
            response = await self._client.post(
                DETECT_URL,
                data={"query": text},
            )
            response.raise_for_status()

        payload = response.json()
        return DetectResult(lang_code=payload["langCode"])


    async def translate(
        self,
        text: str,
        source: LangCode,
        target: LangCode,
    ) -> TranslateResult:
        """source 언어 문장을 target 언어로 번역합니다.

        Args:
            text: 번역할 원문
            source: 원문 언어 코드 (ko | en)
            target: 대상 언어 코드 (ko | en)

        Returns:
            TranslateResult: translated_text
        """
        async with ai_external_call("papago"):
            response = await self._client.post(
                TRANSLATE_URL,
                data={
                    "source": source,
                    "target": target,
                    "text": text,
                },
            )
            response.raise_for_status()

        payload = response.json()
        translated = payload["message"]["result"]["translatedText"]
        return TranslateResult(translated_text=translated)
