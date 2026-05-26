from typing import List
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
import base64

from app.core.llm_manager import ModelName, get_llm_manager


SYSTEM_PROMPT = """You are an expert menu translator and data extractor for foreign tourists visiting South Korea.
Analyze the image and extract the information STRICTLY in the specified JSON format.

[RULES - CRITICAL]
1. NO Autocorrection: Extract the original Korean text EXACTLY as it appears. Do NOT fix typos.
2. English Translation: Provide a natural English translation for the menu name.
3. English Description: Provide a short, easy-to-understand English description of the dish.
4. Price Formatting: Extract the price as an integer. Remove all commas and currency symbols."""

USER_PROMPT = "Extract the menu information according to the rules."

SUPPORTED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/bmp",
    "image/webp",
    "image/tiff",
}


class Menu(BaseModel):
    """메뉴 항목"""
    original_name: str = Field(description="원본 한국어 메뉴명 (오타 포함 그대로)")
    english_name: str = Field(description="영어 번역 메뉴명")
    description: str = Field(description="영어 메뉴 설명")
    price: int = Field(description="가격 (정수, 통화 기호 제거)")


class MenuOcrResult(BaseModel):
    """메뉴 OCR 결과"""
    menus: List[Menu] = Field(description="추출된 메뉴 목록")


class MenuOcrModel:
    """메뉴 OCR 모델 — 이미지에서 메뉴 정보를 추출합니다."""

    def __init__(self):
        self._llm = None


    def load_model(self) -> None:
        """LLMManager에서 Gemini 모델을 가져와 structured output을 설정합니다."""
        manager = get_llm_manager()
        base_llm = manager.get_model(ModelName.GEMINI_2_5_FLASH.value)
        self._llm = base_llm.with_structured_output(MenuOcrResult)


    async def predict(self, image_data: str, mime_type: str) -> MenuOcrResult:
        """
        이미지 데이터로부터 메뉴 정보를 추출합니다.

        Args:
            image_data: base64 인코딩된 이미지 데이터
            mime_type: 이미지 MIME 타입 (e.g. "image/jpeg")

        Returns:
            MenuOcrResult Pydantic 객체
        """
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=[
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_data}",
                        },
                    },
                    {"type": "text", "text": USER_PROMPT},
                ]
            ),
        ]

        return await self._llm.ainvoke(messages)


    async def predict_batch(
        self, images: List[tuple[str, str]]
    ) -> List[MenuOcrResult]:
        """
        여러 이미지를 병렬로 처리합니다.

        Args:
            images: (base64_data, mime_type) 튜플 리스트

        Returns:
            MenuOcrResult 리스트
        """
        batch_inputs = [
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(
                    content=[
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_data}",
                            },
                        },
                        {"type": "text", "text": USER_PROMPT},
                    ]
                ),
            ]
            for image_data, mime_type in images
        ]

        return await self._llm.abatch(batch_inputs)


    @staticmethod
    def encode_bytes(image_bytes: bytes, content_type: str) -> tuple[str, str]:
        """
        이미지 바이트를 base64로 인코딩합니다. (메모리 내 처리, 디스크 저장 없음)

        Args:
            image_bytes: 이미지 원본 바이트 (UploadFile.read()로부터)
            content_type: MIME 타입 (UploadFile.content_type으로부터, e.g. "image/jpeg")

        Returns:
            (base64_data, mime_type) 튜플
        """
        if content_type not in SUPPORTED_MIME_TYPES:
            raise ValueError(
                f"Unsupported image type: {content_type}. "
                f"Supported: {', '.join(sorted(SUPPORTED_MIME_TYPES))}"
            )

        encoded = base64.b64encode(image_bytes).decode("utf-8")
        return encoded, content_type
