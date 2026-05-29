from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from dependency_injector.wiring import Provide, inject

from app.schema.common import MessageResponse
from app.domain.tripmate.service.tripmate_search_history import TripmateSearchHistoryService
from app.domain.tripmate.service.tripmate_post_like import TripmatePostLikeService
from app.domain.tripmate.service.tripmate_post_draft import TripmatePostDraftService
from app.domain.tripmate.service.tripmate_post import TripmatePostService
from app.domain.tripmate.schema.tripmate_post import (
    CreatePostRequest, UpdatePostRequest, SaveDraftRequest,
    PostCreateResponse, PostDetailResponse, PostListResponse,
    ToggleDisplayResponse, LikeResponse, LikedUsersResponse,
    DraftResponse, AuthorResponse,
)
from app.core.logger import get_logger
from app.container import Container


router = APIRouter(prefix="/posts", tags=["여행 메이트 게시글"])
logger = get_logger("tripmate.post")


# ──────────────────── 게시글 CRUD ────────────────────

@router.post("", status_code=201)
@inject
async def create_post(
    request: Request,
    body: CreatePostRequest,
    post_service: TripmatePostService = Depends(Provide[Container.tripmate_post_service]),
) -> PostCreateResponse:
    """게시글 생성"""
    user_id: str = request.state.user_id

    try:
        result = await post_service.create_post(
            user_id=user_id,
            title=body.title,
            content=body.content,
            preferred_age_min=body.preferred_age_min,
            preferred_age_max=body.preferred_age_max,
            preferred_gender=body.preferred_gender,
            region=body.region,
            travel_start_date=body.travel_start_date,
            travel_end_date=body.travel_end_date,
            companion_type=body.companion_type,
            image_urls=body.image_urls,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PostCreateResponse(
        post_id=result.post_id,
        user_id=result.user_id,
        title=result.title,
        content=result.content,
        preferred_age_min=result.preferred_age_min,
        preferred_age_max=result.preferred_age_max,
        preferred_gender=result.preferred_gender,
        region=result.region,
        travel_start_date=result.travel_start_date,
        travel_end_date=result.travel_end_date,
        companion_type=result.companion_type,
        is_displayed=result.is_displayed,
        created_at=result.created_at,
        updated_at=result.updated_at,
        image_urls=result.image_urls,
        profile_image_url=result.profile_image_url,
    )


@router.get("")
@inject
async def get_posts(
    request: Request,
    cursor: Optional[str] = Query(None, description="다음 페이지 커서 (post_id)"),
    post_service: TripmatePostService = Depends(Provide[Container.tripmate_post_service]),
) -> PostListResponse:
    """게시글 목록 조회 (최신순 30개, 커서 페이지네이션)"""
    user_id: str = request.state.user_id

    result = await post_service.get_posts(cursor=cursor, user_id=user_id)
    return PostListResponse(
        posts=[_to_post_response(p) for p in result.posts],
        next_cursor=result.next_cursor,
    )


@router.get("/search")
@inject
async def search_posts(
    request: Request,
    keyword: str = Query(..., min_length=1, description="검색 키워드 (제목, 내용, 작성자)"),
    cursor: Optional[str] = Query(None, description="다음 페이지 커서 (post_id)"),
    post_service: TripmatePostService = Depends(Provide[Container.tripmate_post_service]),
    search_history_service: TripmateSearchHistoryService = Depends(Provide[Container.tripmate_search_history_service]),
) -> PostListResponse:
    """게시글 검색 (제목, 내용, 작성자 닉네임)"""
    user_id: str = request.state.user_id

    try:
        await search_history_service.save_search(user_id=user_id, search_name=keyword)
    except Exception:
        logger.warning("검색 기록 저장 실패: user_id={}, keyword={}", user_id, keyword)

    result = await post_service.search_posts(keyword=keyword, cursor=cursor, user_id=user_id)
    return PostListResponse(
        posts=[_to_post_response(p) for p in result.posts],
        next_cursor=result.next_cursor,
    )


# ──────────────────── 임시저장 ────────────────────

@router.put("/draft")
@inject
async def save_draft(
    request: Request,
    body: SaveDraftRequest,
    draft_service: TripmatePostDraftService = Depends(Provide[Container.tripmate_post_draft_service]),
) -> DraftResponse:
    """게시글 임시저장 (30초마다 자동 호출)"""
    user_id: str = request.state.user_id

    result = await draft_service.save_draft(
        user_id=user_id,
        title=body.title,
        content=body.content,
        preferred_age_min=body.preferred_age_min,
        preferred_age_max=body.preferred_age_max,
        preferred_gender=body.preferred_gender,
        region=body.region,
        travel_start_date=body.travel_start_date,
        travel_end_date=body.travel_end_date,
        companion_type=body.companion_type,
        image_urls=body.image_urls,
    )
    return _to_draft_response(result)


@router.get("/draft")
@inject
async def get_draft(
    request: Request,
    draft_service: TripmatePostDraftService = Depends(Provide[Container.tripmate_post_draft_service]),
) -> Optional[DraftResponse]:
    """임시저장 조회 (있으면 반환, 없으면 null)"""
    user_id: str = request.state.user_id

    result = await draft_service.get_draft(user_id)
    if result is None:
        return None
    return _to_draft_response(result)


@router.delete("/draft")
@inject
async def delete_draft(
    request: Request,
    draft_service: TripmatePostDraftService = Depends(Provide[Container.tripmate_post_draft_service]),
) -> MessageResponse:
    """임시저장 수동 삭제"""
    user_id: str = request.state.user_id

    await draft_service.delete_draft(user_id)
    return MessageResponse(message="임시저장이 삭제되었습니다.")


# ──────────────────── 게시글 단건/수정/삭제 ────────────────────

@router.get("/{post_id}")
@inject
async def get_post(
    request: Request,
    post_id: str,
    post_service: TripmatePostService = Depends(Provide[Container.tripmate_post_service]),
) -> PostDetailResponse:
    """게시글 단건 조회"""
    user_id: str = request.state.user_id

    try:
        result = await post_service.get_post(post_id=post_id, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return _to_post_response(result)


@router.put("/{post_id}")
@inject
async def update_post(
    request: Request,
    post_id: str,
    body: UpdatePostRequest,
    post_service: TripmatePostService = Depends(Provide[Container.tripmate_post_service]),
) -> PostDetailResponse:
    """게시물 수정"""
    user_id: str = request.state.user_id

    try:
        result = await post_service.update_post(
            post_id=post_id,
            user_id=user_id,
            title=body.title,
            content=body.content,
            preferred_age_min=body.preferred_age_min,
            preferred_age_max=body.preferred_age_max,
            preferred_gender=body.preferred_gender,
            region=body.region,
            travel_start_date=body.travel_start_date,
            travel_end_date=body.travel_end_date,
            companion_type=body.companion_type,
            image_urls=body.image_urls,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return _to_post_response(result)


@router.delete("/{post_id}", status_code=200)
@inject
async def delete_post(
    request: Request,
    post_id: str,
    post_service: TripmatePostService = Depends(Provide[Container.tripmate_post_service]),
) -> MessageResponse:
    """게시글 삭제"""
    user_id: str = request.state.user_id

    try:
        await post_service.delete_post(post_id=post_id, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return MessageResponse(message="게시글이 삭제되었습니다.")


# ──────────────────── Display 토글 ────────────────────

@router.patch("/{post_id}/display")
@inject
async def toggle_display(
    request: Request,
    post_id: str,
    post_service: TripmatePostService = Depends(Provide[Container.tripmate_post_service]),
) -> ToggleDisplayResponse:
    """게시글 표시 여부 토글 (활성화 ↔ 비활성화)"""
    user_id: str = request.state.user_id

    try:
        is_displayed = await post_service.toggle_display(post_id=post_id, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return ToggleDisplayResponse(post_id=post_id, is_displayed=is_displayed)


# ──────────────────── 좋아요 ─────────────────────

@router.post("/{post_id}/like", status_code=201)
@inject
async def add_like(
    request: Request,
    post_id: str,
    like_service: TripmatePostLikeService = Depends(Provide[Container.tripmate_post_like_service]),
) -> LikeResponse:
    """게시글 좋아요"""
    user_id: str = request.state.user_id

    try:
        like_count = await like_service.add_like(user_id=user_id, post_id=post_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return LikeResponse(post_id=post_id, like_count=like_count)


@router.delete("/{post_id}/like")
@inject
async def remove_like(
    request: Request,
    post_id: str,
    like_service: TripmatePostLikeService = Depends(Provide[Container.tripmate_post_like_service]),
) -> LikeResponse:
    """게시글 좋아요 취소"""
    user_id: str = request.state.user_id

    try:
        like_count = await like_service.remove_like(user_id=user_id, post_id=post_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return LikeResponse(post_id=post_id, like_count=like_count)


@router.get("/{post_id}/likes")
@inject
async def get_liked_users(
    post_id: str,
    like_service: TripmatePostLikeService = Depends(Provide[Container.tripmate_post_like_service]),
) -> LikedUsersResponse:
    """게시글 좋아요 누른 유저 목록"""
    try:
        user_ids = await like_service.get_liked_user_ids(post_id=post_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return LikedUsersResponse(post_id=post_id, user_ids=user_ids)


# ──────────────────── 내부 유틸 ────────────────────

def _to_post_response(dto) -> PostDetailResponse:
    return PostDetailResponse(
        post_id=dto.post_id,
        user_id=dto.user_id,
        author=AuthorResponse(
            user_name=dto.author.user_name,
            age=dto.author.age,
            gender=dto.author.gender,
            nationality=dto.author.nationality,
        ),
        title=dto.title,
        content=dto.content,
        preferred_age_min=dto.preferred_age_min,
        preferred_age_max=dto.preferred_age_max,
        preferred_gender=dto.preferred_gender,
        region=dto.region,
        travel_start_date=dto.travel_start_date,
        travel_end_date=dto.travel_end_date,
        companion_type=dto.companion_type,
        is_displayed=dto.is_displayed,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
        like_count=dto.like_count,
        is_liked=dto.is_liked,
        image_urls=dto.image_urls,
        profile_image_url=dto.profile_image_url,
    )


def _to_draft_response(draft) -> DraftResponse:
    return DraftResponse(
        user_id=draft.user_id,
        title=draft.title,
        content=draft.content,
        preferred_age_min=draft.preferred_age_min,
        preferred_age_max=draft.preferred_age_max,
        preferred_gender=draft.preferred_gender,
        region=draft.region,
        travel_start_date=draft.travel_start_date,
        travel_end_date=draft.travel_end_date,
        companion_type=draft.companion_type,
        image_urls=draft.image_urls,
        updated_at=draft.updated_at,
    )
