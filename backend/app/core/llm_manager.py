from typing import Dict, List
from langchain_google_genai import ChatGoogleGenerativeAI
import httpx
from functools import lru_cache
from enum import Enum

from app.core.instrumentation import GeminiInstrumentationHandler
from app.config.setting import settings


class ModelName(str, Enum):
    """사용 가능한 Gemini 모델 이름"""
    GEMINI_2_0_FLASH = "gemini-2.0-flash"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_PRO = "gemini-2.5-pro"

    @classmethod
    def values(cls) -> List[str]:
        """모든 모델 이름을 리스트로 반환"""
        return [model.value for model in cls]


class LLMManager:
    """Gemini LLM 모델을 관리하는 클래스"""

    def __init__(self):
        self._models: Dict[str, ChatGoogleGenerativeAI] = {}
        self._initialized = False


    def initialize(self) -> bool:
        """모든 Gemini 모델을 초기화합니다.

        모든 ChatGoogleGenerativeAI 인스턴스에 GeminiInstrumentationHandler 를 callbacks 로
        부착해 external_call duration / result + token_usage 메트릭을 자동 수집한다.
        """
        if not self._initialized:

            handler = GeminiInstrumentationHandler()
            for model in ModelName:
                self._models[model.value] = ChatGoogleGenerativeAI(
                    model=model.value,
                    google_api_key=settings.GOOGLE_GEMINI_API_KEY,
                    callbacks=[handler],
                )
            self._initialized = True

        return self._initialized


    def get_model(self, model_name: str) -> ChatGoogleGenerativeAI:
        """모델 이름으로 Gemini 모델을 반환합니다."""
        if not self._initialized:
            self.initialize()

        if model_name not in self._models:
            raise ValueError(
                f"Model '{model_name}' not found. "
                f"Available models: {', '.join(ModelName.values())}"
            )

        return self._models[model_name]


    async def check_connection(self) -> bool:
        """Google Gemini API 연결 상태를 확인합니다."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models"
                    f"?key={settings.GOOGLE_GEMINI_API_KEY}",
                    timeout=5.0,
                )
                return response.status_code == 200
        except Exception:
            return False


    def is_initialized(self) -> bool:
        """초기화 상태를 반환합니다."""
        return self._initialized


@lru_cache(maxsize=1)
def get_llm_manager() -> LLMManager:
    """LLMManager 싱글톤 인스턴스를 반환합니다."""
    return LLMManager()
