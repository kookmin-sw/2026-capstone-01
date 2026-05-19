from typing import List
from fastapi import APIRouter, HTTPException, Request, Depends, UploadFile, File
from dependency_injector.wiring import Provide, inject

from app.schema.common import MessageResponse
from app.domain.tripmate.service.tripmate_image import TripmateImageService
from app.domain.tripmate.schema.tripmate_image import (
    ImageUploadResponse, ImageUploadListResponse, CleanupResponse,
)
from app.core.logger import get_logger
from app.container import Container


router = APIRouter(prefix="/images", tags=["여행 메이트 이미지"])
logger = get_logger("tripmate.image")

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
_MAX_FILE_COUNT = 10


# ──────────────────── 이미지 업로드 ────────────────────

@router.post("", status_code=201)
@inject
async def upload_images(
    request: Request,
    files: List[UploadFile] = File(..., description="업로드할 이미지 파일 목록"),
    image_service: TripmateImageService = Depends(Provide[Container.tripmate_image_service]),
) -> ImageUploadListResponse:
    """이미지 업로드 (다건, 최대 10개 / 파일당 10MB / jpeg·png·webp·gif만 허용)"""
    user_id: str = request.state.user_id

    if len(files) > _MAX_FILE_COUNT:
        raise HTTPException(status_code=400, detail=f"이미지는 최대 {_MAX_FILE_COUNT}개까지 업로드할 수 있습니다.")

    for f in files:
        if f.content_type not in _ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"허용되지 않는 파일 형식입니다: {f.content_type} (jpeg, png, webp, gif만 가능)",
            )
        contents = await f.read()
        if len(contents) > _MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"파일 크기가 10MB를 초과합니다: {f.filename}",
            )
        await f.seek(0)

    file_tuples = [
        (f.file, f.filename or "image", f.content_type or "image/jpeg")
        for f in files
    ]

    try:
        results = await image_service.upload_images(user_id=user_id, files=file_tuples)
    except Exception as e:
        logger.error("이미지 업로드 실패 (user_id={}): {}", user_id, e)
        raise HTTPException(status_code=500, detail="이미지 업로드에 실패했습니다.")

    return ImageUploadListResponse(
        images=[
            ImageUploadResponse(image_id=r.image_id, image_url=r.image_url)
            for r in results
        ]
    )


# # ──────────────────── 이미지 단건 삭제 ────────────────────
# # 현재 미사용
# @router.delete("/{image_id}")
# @inject
# async def delete_image(
#     request: Request,
#     image_id: str,
#     image_service: TripmateImageService = Depends(Provide[Container.tripmate_image_service]),
# ) -> MessageResponse:
#     """이미지 단건 삭제 (Object Storage + MongoDB 메타데이터 동시 삭제)"""
#     user_id: str = request.state.user_id

#     try:
#         await image_service.delete_image(user_id=user_id, image_id=image_id)
#     except ValueError as e:
#         raise HTTPException(status_code=404, detail=str(e))
#     except PermissionError as e:
#         raise HTTPException(status_code=403, detail=str(e))

#     return MessageResponse(message="이미지가 삭제되었습니다.")


# ──────────────────── 고아 이미지 정리 ────────────────────

@router.post("/cleanup", status_code=200)
@inject
async def cleanup_orphaned_images(
    request: Request,
    image_service: TripmateImageService = Depends(Provide[Container.tripmate_image_service]),
) -> CleanupResponse:
    """
    고아 이미지 정리 — 앱에 연결되는 API가 아닙니다 (관리/운영용).

    업로드되었으나 게시글(tripmate_post_image)에도 임시저장(tripmate_post_draft)에도
    참조되지 않는 이미지를 Object Storage와 MongoDB에서 일괄 삭제합니다.
    """
    user_id: str = request.state.user_id

    try:
        deleted_count = await image_service.cleanup_orphaned_images(user_id=user_id)
    except Exception as e:
        logger.error("고아 이미지 정리 실패 (user_id={}): {}", user_id, e)
        raise HTTPException(status_code=500, detail="고아 이미지 정리에 실패했습니다.")

    return CleanupResponse(deleted_count=deleted_count)
