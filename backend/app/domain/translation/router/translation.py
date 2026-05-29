from fastapi import APIRouter, Depends, HTTPException, Request
from dependency_injector.wiring import Provide, inject

from app.domain.translation.service.translation import TranslationService
from app.domain.translation.service.exception import (
    TranslationUnreachableError,
    TranslationVendorError,
)
from app.domain.translation.schema.translation import (
    DetectRequest,
    DetectResponse,
    TranslateRequest,
    TranslateResponse,
)
from app.core.logger import get_logger
from app.container import Container


router = APIRouter(tags=["번역"])
logger = get_logger("translation")


# ──────────────────── 언어 감지 ────────────────────

@router.post("/detect", status_code=200)
@inject
async def detect_language(
    request: Request,
    body: DetectRequest,
    translation_service: TranslationService = Depends(Provide[Container.translation_service]),
) -> DetectResponse:
    """입력 문장의 언어를 감지합니다 (ko / en)."""
    try:
        result = await translation_service.detect(body.text)
    except TranslationVendorError as e:
        logger.error("언어 감지 실패 (status={}): {}", e.status_code, e.body)
        raise HTTPException(status_code=502, detail="언어 감지에 실패했습니다.")
    except TranslationUnreachableError as e:
        logger.error("언어 감지 네트워크 오류: {}", e)
        raise HTTPException(status_code=504, detail="번역 서버에 연결할 수 없습니다.")

    return DetectResponse(lang_code=result.lang_code)


# ──────────────────── 번역 ────────────────────

@router.post("/translate", status_code=200)
@inject
async def translate_text(
    request: Request,
    body: TranslateRequest,
    translation_service: TranslationService = Depends(Provide[Container.translation_service]),
) -> TranslateResponse:
    """source 언어 문장을 target 언어로 번역합니다."""
    if body.source == body.target:
        raise HTTPException(
            status_code=400,
            detail="source 와 target 언어가 동일합니다.",
        )

    try:
        result = await translation_service.translate(body.text, body.source, body.target)
    except TranslationVendorError as e:
        logger.error("번역 실패 (status={}): {}", e.status_code, e.body)
        raise HTTPException(status_code=502, detail="번역에 실패했습니다.")
    except TranslationUnreachableError as e:
        logger.error("번역 네트워크 오류: {}", e)
        raise HTTPException(status_code=504, detail="번역 서버에 연결할 수 없습니다.")

    return TranslateResponse(translated_text=result.translated_text)
