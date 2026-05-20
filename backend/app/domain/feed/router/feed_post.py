"""피드 게시물 라우터 — 본인 피드 CRUD. 타 유저 피드는 `feed_user.py` 별도."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends, UploadFile, File, Form, Query
from dependency_injector.wiring import Provide, inject

from app.schema.common import MessageResponse
from app.domain.feed.service.feed_post import FeedPostService
from app.domain.feed.service.exception import FeedNotFoundError
from app.domain.feed.schema.feed_post import (
    FeedPostResponse, FeedPostListResponse,
    UpdateVisibilityRequest, UpdateCaptionRequest,
)
from app.domain.feed.model.feed_post import FeedVisibility, CAPTION_MAX_LENGTH
from app.domain.feed.dto.feed_post import FeedPostData, FeedPostListData
from app.core.logger import get_logger
from app.container import Container


router = APIRouter(tags=["내 소유 피드 CRUD"])
logger = get_logger("feed.post.router")


# GIF 제외 (정지 이미지 전용 정책). thumbnail.py 의 화이트리스트와 일치 — 라우터가 fast-fail,
# thumbnail 은 defense-in-depth.
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


# ──────────────────── 업로드 ────────────────────

@router.post("/posts", status_code=201)
@inject
async def upload_post(
    request: Request,
    file: UploadFile = File(..., description="업로드할 이미지 (jpg/png/webp, ≤10MB)"),
    visibility: FeedVisibility = Form(
        FeedVisibility.PUBLIC, description="공개 범위 (private / friends / public). 기본 public.",
    ),
    caption: Optional[str] = Form(
        None, max_length=CAPTION_MAX_LENGTH,
        description=f"캡션 (최대 {CAPTION_MAX_LENGTH}자, 빈 문자열/공백만 시 캡션 없음으로 저장)",
    ),
    feed_service: FeedPostService = Depends(Provide[Container.feed_post_service]),
) -> FeedPostResponse:
    """피드 게시물 업로드 (multipart/form-data). content-type → 파일 크기 → 서비스 순 검증."""
    user_id: str = request.state.user_id

    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"허용되지 않는 파일 형식입니다: {file.content_type} (jpeg, png, webp만 가능)",
        )

    contents = await file.read()
    if len(contents) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"파일 크기가 {_MAX_FILE_SIZE // (1024 * 1024)}MB 를 초과합니다.",
        )

    try:
        post = await feed_service.upload_post(
            user_id=user_id,
            file_bytes=contents,
            visibility=visibility,
            caption=caption,
        )
    except ValueError as e:
        # Pillow 디코딩 실패 / 미지원 포맷 / 해상도 초과 등.
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("피드 업로드 실패 (user_id={}): {}", user_id, e)
        raise HTTPException(status_code=500, detail="피드 업로드에 실패했습니다.")

    return _to_response(post)


# ──────────────────── 조회 ────────────────────

@router.get("/me")
@inject
async def get_my_feed(
    request: Request,
    cursor: Optional[str] = Query(None, description="다음 페이지 커서 (post_id)"),
    feed_service: FeedPostService = Depends(Provide[Container.feed_post_service]),
) -> FeedPostListResponse:
    """본인 피드 — 모든 visibility, 커서 페이지네이션."""
    user_id: str = request.state.user_id
    result = await feed_service.get_my_feed(user_id=user_id, cursor=cursor)
    return _to_list_response(result)


@router.get("/posts/{post_id}")
@inject
async def get_post(
    request: Request,
    post_id: str,
    feed_service: FeedPostService = Depends(Provide[Container.feed_post_service]),
) -> FeedPostResponse:
    """본인 게시물 단건."""
    user_id: str = request.state.user_id
    try:
        post = await feed_service.get_my_post(user_id=user_id, post_id=post_id)
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return _to_response(post)


# ──────────────────── 변경 ────────────────────

@router.patch("/posts/{post_id}/visibility")
@inject
async def update_visibility(
    request: Request,
    post_id: str,
    body: UpdateVisibilityRequest,
    feed_service: FeedPostService = Depends(Provide[Container.feed_post_service]),
) -> FeedPostResponse:
    """공개 범위 변경 — 본인만, 즉시 반영."""
    user_id: str = request.state.user_id
    try:
        post = await feed_service.update_visibility(
            user_id=user_id, post_id=post_id, visibility=body.visibility,
        )
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return _to_response(post)


@router.patch("/posts/{post_id}/caption")
@inject
async def update_caption(
    request: Request,
    post_id: str,
    body: UpdateCaptionRequest,
    feed_service: FeedPostService = Depends(Provide[Container.feed_post_service]),
) -> FeedPostResponse:
    """캡션 변경 — 본인만. body.caption 이 null / 빈 문자열 / 공백만이면 캡션 삭제."""
    user_id: str = request.state.user_id
    try:
        post = await feed_service.update_caption(
            user_id=user_id, post_id=post_id, caption=body.caption,
        )
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return _to_response(post)


# ──────────────────── 삭제 ────────────────────

@router.delete("/posts/{post_id}")
@inject
async def delete_post(
    request: Request,
    post_id: str,
    feed_service: FeedPostService = Depends(Provide[Container.feed_post_service]),
) -> MessageResponse:
    """본인 게시물 삭제 — 원본 + 썸네일 일괄 정리, 좋아요/댓글 cascade."""
    user_id: str = request.state.user_id
    try:
        await feed_service.delete_post(user_id=user_id, post_id=post_id)
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return MessageResponse(message="피드 게시물이 삭제되었습니다.")


# ──────────────────── 내부 유틸 ────────────────────

def _to_response(post: FeedPostData) -> FeedPostResponse:
    """DTO → Response 1:1."""
    return FeedPostResponse(
        post_id=post.post_id,
        user_id=post.user_id,
        visibility=post.visibility,
        caption=post.caption,
        original_url=post.original_url,
        thumbnail_small_url=post.thumbnail_small_url,
        thumbnail_medium_url=post.thumbnail_medium_url,
        like_count=post.like_count,
        comment_count=post.comment_count,
        is_liked=post.is_liked,
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


def _to_list_response(result: FeedPostListData) -> FeedPostListResponse:
    return FeedPostListResponse(
        posts=[_to_response(p) for p in result.posts],
        next_cursor=result.next_cursor,
    )
