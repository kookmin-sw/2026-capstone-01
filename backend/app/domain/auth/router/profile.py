from fastapi import APIRouter, HTTPException, Request, Depends, UploadFile, File
from dependency_injector.wiring import Provide, inject

from app.schema.common import MessageResponse
from app.domain.auth.service.profile import ProfileService
from app.domain.auth.service.exception import (
    ProfileNotRegisteredError,
    ProfileImageAlreadyExistsError,
    ProfileImageNotFoundError,
)
from app.domain.auth.schema.profile import (
    ProfileResponse,
    ProfileUpdateRequest,
    ProfileImageResponse,
    OtherUserProfileResponse,
    OtherUserProfileListResponse,
)
from app.core.logger import get_logger
from app.container import Container


router = APIRouter(prefix="/profile", tags=["프로필"])
logger = get_logger("auth.profile")


_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB (프로필은 게시글보다 작게)


def _validate_content_type(file: UploadFile) -> None:
    """content-type 검증 (read 전 fast-fail)."""
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"허용되지 않는 파일 형식입니다: {file.content_type} (jpeg, png, webp, gif만 가능)",
        )


def _validate_size(contents: bytes, file_name: str | None) -> None:
    """크기 검증 (read 후)."""
    if len(contents) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"파일 크기가 5MB를 초과합니다: {file_name}",
        )


@router.get("/me")
@inject
async def get_my_profile(
    request: Request,
    profile_service: ProfileService = Depends(Provide[Container.profile_service]),
) -> ProfileResponse:
    """내 프로필 조회"""
    user_id: str = request.state.user_id

    try:
        profile = await profile_service.get_my_profile(user_id)
    except ProfileNotRegisteredError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        # "존재하지 않는 유저입니다." 등
        raise HTTPException(status_code=404, detail=str(e))

    return ProfileResponse(
        user_id=profile.user_id,
        auth_provider=profile.auth_provider.value,
        status=profile.status.value,
        email=profile.email,
        user_name=profile.user_name,
        phone_number=profile.phone_number,
        age=profile.age,
        gender=profile.gender,
        travel_styles=profile.travel_styles,
        nationality=profile.nationality,
        profile_image_url=profile.profile_image_url,
        notification_muted=profile.notification_muted,
    )


@router.patch("/me")
@inject
async def update_my_profile(
    request: Request,
    body: ProfileUpdateRequest,
    profile_service: ProfileService = Depends(Provide[Container.profile_service]),
) -> ProfileResponse:
    """내 프로필 수정 — 변경할 필드만 포함하는 부분 수정.

    수정 가능: email, user_name, phone_number, age, gender, nationality, travel_styles
    수정 불가 (별도 엔드포인트):
        - profile_image_url → POST/PUT/DELETE /profile/image
        - notification_muted → /notification/mute
        - status            → /auth/withdraw
        - auth_provider     → 영구 불변
    """
    user_id: str = request.state.user_id

    updates = body.model_dump(exclude_none=True)

    try:
        profile = await profile_service.update_profile(user_id, updates)
    except ProfileNotRegisteredError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return ProfileResponse(
        user_id=profile.user_id,
        auth_provider=profile.auth_provider.value,
        status=profile.status.value,
        email=profile.email,
        user_name=profile.user_name,
        phone_number=profile.phone_number,
        age=profile.age,
        gender=profile.gender,
        travel_styles=profile.travel_styles,
        nationality=profile.nationality,
        profile_image_url=profile.profile_image_url,
        notification_muted=profile.notification_muted,
    )


@router.get("/all")
@inject
async def get_all_other_users(
    request: Request,
    profile_service: ProfileService = Depends(Provide[Container.profile_service]),
) -> OtherUserProfileListResponse:
    """본인을 제외한 ACTIVE 유저 전체 목록"""
    user_id: str = request.state.user_id

    profiles = await profile_service.get_all_other_users(user_id)

    return OtherUserProfileListResponse(
        users=[
            OtherUserProfileResponse(
                user_id=p.user_id,
                user_name=p.user_name,
                nationality=p.nationality,
                travel_styles=p.travel_styles,
                profile_image_url=p.profile_image_url,
            )
            for p in profiles
        ]
    )


# ──────────────────── 프로필 이미지 CRUD (유저당 1장 정책) ────────────────────

@router.post("/image", status_code=201)
@inject
async def add_profile_image(
    request: Request,
    file: UploadFile = File(..., description="업로드할 프로필 이미지 (jpeg/png/webp/gif, 최대 5MB)"),
    profile_service: ProfileService = Depends(Provide[Container.profile_service]),
) -> ProfileImageResponse:
    """프로필 이미지 추가 — 이미 있으면 409. 수정은 PUT 사용."""
    user_id: str = request.state.user_id

    _validate_content_type(file)
    contents = await file.read()
    _validate_size(contents, file.filename)
    await file.seek(0)

    try:
        result = await profile_service.add_profile_image(
            user_id=user_id,
            file=file.file,
            file_name=file.filename or "profile",
            content_type=file.content_type or "image/jpeg",
        )
    except ProfileImageAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ProfileNotRegisteredError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("프로필 이미지 추가 실패 (user_id={}): {}", user_id, e)
        raise HTTPException(status_code=500, detail="프로필 이미지 업로드에 실패했습니다.")

    return ProfileImageResponse(profile_image_url=result.profile_image_url)


@router.put("/image")
@inject
async def update_profile_image(
    request: Request,
    file: UploadFile = File(..., description="교체할 프로필 이미지 (jpeg/png/webp/gif, 최대 5MB)"),
    profile_service: ProfileService = Depends(Provide[Container.profile_service]),
) -> ProfileImageResponse:
    """프로필 이미지 수정 — 없으면 404. 이전 파일은 자동 삭제."""
    user_id: str = request.state.user_id

    _validate_content_type(file)
    contents = await file.read()
    _validate_size(contents, file.filename)
    await file.seek(0)

    try:
        result = await profile_service.update_profile_image(
            user_id=user_id,
            file=file.file,
            file_name=file.filename or "profile",
            content_type=file.content_type or "image/jpeg",
        )
    except ProfileImageNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ProfileNotRegisteredError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("프로필 이미지 수정 실패 (user_id={}): {}", user_id, e)
        raise HTTPException(status_code=500, detail="프로필 이미지 수정에 실패했습니다.")

    return ProfileImageResponse(profile_image_url=result.profile_image_url)


@router.delete("/image")
@inject
async def delete_profile_image(
    request: Request,
    profile_service: ProfileService = Depends(Provide[Container.profile_service]),
) -> MessageResponse:
    """프로필 이미지 삭제 — 없으면 404."""
    user_id: str = request.state.user_id

    try:
        await profile_service.delete_profile_image(user_id)
    except ProfileImageNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ProfileNotRegisteredError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("프로필 이미지 삭제 실패 (user_id={}): {}", user_id, e)
        raise HTTPException(status_code=500, detail="프로필 이미지 삭제에 실패했습니다.")

    return MessageResponse(message="프로필 이미지가 삭제되었습니다.")
