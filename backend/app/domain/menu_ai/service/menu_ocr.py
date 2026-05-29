from typing import List
from google.api_core.exceptions import (
    GoogleAPICallError,
    PermissionDenied,
    ResourceExhausted,
    Unauthenticated,
)

from app.domain.menu_ai.service.exception import (
    MenuOcrCredentialExpiredError,
    MenuOcrQuotaExceededError,
    MenuOcrVendorError,
)
from app.domain.menu_ai.dto.menu_ocr import MenuData, MenuOcrData, MenuOcrBatchData
from app.core.logger import get_logger
from app.core.ai.menu_ocr.v1.model import MenuOcrResult
from app.core.ai.menu_ocr.load import MenuOcr


logger = get_logger("menu_ai.ocr.service")


class MenuOcrService:
    def __init__(self):
        self._ocr = MenuOcr()

    # ──────────────────── 단건 OCR ────────────────────

    async def ocr_single(self, image_bytes: bytes, content_type: str) -> MenuOcrData:
        """
        이미지 한 장에서 메뉴 정보를 추출합니다.

        1. MenuOcr 모델 호출
        2. DTO 변환 후 반환
        """
        try:
            result = await self._ocr.invoke(image_bytes, content_type)
        except (Unauthenticated, PermissionDenied) as e:
            raise MenuOcrCredentialExpiredError(str(e)) from e
        except ResourceExhausted as e:
            raise MenuOcrQuotaExceededError(str(e)) from e
        except GoogleAPICallError as e:
            raise MenuOcrVendorError(str(e)) from e
        return self._to_dto(result)

    # ──────────────────── 다건 OCR ────────────────────

    async def ocr_batch(
        self, images: List[tuple[bytes, str]]
    ) -> MenuOcrBatchData:
        """
        여러 이미지에서 메뉴 정보를 병렬 추출합니다.

        1. MenuOcr 배치 모델 호출
        2. DTO 변환 후 반환
        """
        try:
            results = await self._ocr.invoke_batch(images)
        except (Unauthenticated, PermissionDenied) as e:
            raise MenuOcrCredentialExpiredError(str(e)) from e
        except ResourceExhausted as e:
            raise MenuOcrQuotaExceededError(str(e)) from e
        except GoogleAPICallError as e:
            raise MenuOcrVendorError(str(e)) from e
        return MenuOcrBatchData(
            results=[self._to_dto(r) for r in results]
        )

    # ──────────────────── 내부 변환 유틸 ────────────────────

    @staticmethod
    def _to_dto(result: MenuOcrResult) -> MenuOcrData:
        return MenuOcrData(
            menus=[
                MenuData(
                    original_name=menu.original_name,
                    english_name=menu.english_name,
                    description=menu.description,
                    price=menu.price,
                )
                for menu in result.menus
            ]
        )
