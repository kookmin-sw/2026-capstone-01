from typing import List
import time

from app.core.instrumentation import ai_inference, ai_model_load_duration_set
from app.core.ai.menu_ocr.v1.model import MenuOcrModel, MenuOcrResult


class MenuOcr:
    """메뉴 OCR — 이미지에서 메뉴 정보를 추출합니다."""

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
        self._model = MenuOcrModel()
        self._model.load_model()
        ai_model_load_duration_set("menu_ocr", time.perf_counter() - started)
        self._initialized = True


    async def invoke(self, image_bytes: bytes, content_type: str) -> MenuOcrResult:
        """
        추론 요청의 단일 진입점.

        Args:
            image_bytes: 이미지 원본 바이트 (UploadFile.read()로부터)
            content_type: MIME 타입 (UploadFile.content_type, e.g. "image/jpeg")

        Returns:
            MenuOcrResult:
                menus: list[Menu]
                    - original_name: str
                    - english_name: str
                    - description: str
                    - price: int
        """
        if not self._initialized:
            raise RuntimeError("모델이 로드되지 않았습니다.")

        async with ai_inference("menu_ocr"):
            image_data, mime_type = self._model.encode_bytes(image_bytes, content_type)
            return await self._model.predict(image_data, mime_type)


    async def invoke_batch(
        self, images: List[tuple[bytes, str]]
    ) -> List[MenuOcrResult]:
        """
        여러 이미지를 병렬로 처리합니다.

        Args:
            images: (image_bytes, content_type) 튜플 리스트
                    e.g. [(await file1.read(), file1.content_type), ...]

        Returns:
            MenuOcrResult 리스트 (입력 순서와 동일)
        """
        if not self._initialized:
            raise RuntimeError("모델이 로드되지 않았습니다.")

        async with ai_inference("menu_ocr"):
            encoded = [
                self._model.encode_bytes(image_bytes, content_type)
                for image_bytes, content_type in images
            ]

            return await self._model.predict_batch(encoded)
