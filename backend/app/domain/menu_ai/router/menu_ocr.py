from typing import List
from fastapi import APIRouter, HTTPException, Request, Depends, UploadFile, File
from dependency_injector.wiring import Provide, inject

from app.domain.menu_ai.service.menu_ocr import MenuOcrService
from app.domain.menu_ai.service.exception import (
    MenuOcrCredentialExpiredError,
    MenuOcrQuotaExceededError,
    MenuOcrVendorError,
)
from app.domain.menu_ai.schema.menu_ocr import (
    MenuResponse, MenuOcrResponse, MenuOcrBatchResponse,
)
from app.core.logger import get_logger
from app.container import Container


router = APIRouter(prefix="/ocr", tags=["메뉴 OCR"])
logger = get_logger("menu_ai.ocr")

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/gif", "image/bmp", "image/webp", "image/tiff"}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
_MAX_FILE_COUNT = 5


# ──────────────────── 단건 OCR ────────────────────

@router.post("", status_code=200)
@inject
async def ocr_menu(
    request: Request,
    file: UploadFile = File(..., description="메뉴 이미지 파일"),
    ocr_service: MenuOcrService = Depends(Provide[Container.menu_ocr_service]),
) -> MenuOcrResponse:
    """메뉴 이미지 1장에서 메뉴 정보를 추출합니다."""
    _validate_file(file)
    image_bytes = await file.read()
    _validate_file_size(image_bytes, file.filename)

    try:
        result = await ocr_service.ocr_single(image_bytes, file.content_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MenuOcrCredentialExpiredError as e:
        logger.critical("Gemini 인증 만료 / 권한 거부: {}", e)
        raise HTTPException(status_code=503, detail="메뉴 인식 서비스가 일시 중단되었습니다.")
    except MenuOcrQuotaExceededError as e:
        logger.warning("Gemini 쿼터 소진: {}", e)
        raise HTTPException(status_code=429, detail="요청이 많아 처리하지 못했습니다. 잠시 후 다시 시도해주세요.")
    except MenuOcrVendorError as e:
        logger.error("Gemini 벤더 오류: {}", e)
        raise HTTPException(status_code=502, detail="메뉴 인식에 실패했습니다.")

    return _to_ocr_response(result)


# ──────────────────── 다건 OCR ────────────────────

@router.post("/batch", status_code=200)
@inject
async def ocr_menu_batch(
    request: Request,
    files: List[UploadFile] = File(..., description="메뉴 이미지 파일 목록"),
    ocr_service: MenuOcrService = Depends(Provide[Container.menu_ocr_service]),
) -> MenuOcrBatchResponse:
    """여러 메뉴 이미지에서 메뉴 정보를 병렬 추출합니다. (최대 5장)"""
    if len(files) > _MAX_FILE_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"이미지는 최대 {_MAX_FILE_COUNT}개까지 업로드할 수 있습니다.",
        )

    images = []
    for f in files:
        _validate_file(f)
        image_bytes = await f.read()
        _validate_file_size(image_bytes, f.filename)
        images.append((image_bytes, f.content_type))

    try:
        result = await ocr_service.ocr_batch(images)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MenuOcrCredentialExpiredError as e:
        logger.critical("Gemini 인증 만료 / 권한 거부 (batch): {}", e)
        raise HTTPException(status_code=503, detail="메뉴 인식 서비스가 일시 중단되었습니다.")
    except MenuOcrQuotaExceededError as e:
        logger.warning("Gemini 쿼터 소진 (batch): {}", e)
        raise HTTPException(status_code=429, detail="요청이 많아 처리하지 못했습니다. 잠시 후 다시 시도해주세요.")
    except MenuOcrVendorError as e:
        logger.error("Gemini 벤더 오류 (batch): {}", e)
        raise HTTPException(status_code=502, detail="메뉴 인식에 실패했습니다.")

    return MenuOcrBatchResponse(
        results=[_to_ocr_response(r) for r in result.results]
    )


# ──────────────────── 내부 유틸 ────────────────────

def _validate_file(file: UploadFile) -> None:
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"허용되지 않는 파일 형식입니다: {file.content_type} "
                   f"(jpeg, png, gif, bmp, webp, tiff만 가능)",
        )


def _validate_file_size(image_bytes: bytes, filename: str | None) -> None:
    if len(image_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"파일 크기가 10MB를 초과합니다: {filename}",
        )


def _to_ocr_response(dto) -> MenuOcrResponse:
    return MenuOcrResponse(
        menus=[
            MenuResponse(
                original_name=m.original_name,
                english_name=m.english_name,
                description=m.description,
                price=m.price,
            )
            for m in dto.menus
        ]
    )
