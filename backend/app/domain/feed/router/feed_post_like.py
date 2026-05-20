"""피드 좋아요 라우터. 본인 글에 본인 좋아요 허용 (인스타와 동일)."""
from fastapi import APIRouter, HTTPException, Request, Depends
from dependency_injector.wiring import Provide, inject

from app.domain.feed.service.feed_post_like import FeedPostLikeService
from app.domain.feed.service.exception import FeedNotFoundError
from app.domain.feed.schema.feed_post_like import (
    LikedUserItem,
    LikedUsersResponse,
    LikeResponse,
)
from app.domain.feed.dto.feed_post_like import LikedUserData
from app.container import Container


router = APIRouter(tags=["피드 좋아요"])


# ──────────────────── 추가 ────────────────────

@router.post("/posts/{post_id}/like", status_code=201)
@inject
async def add_like(
    request: Request,
    post_id: str,
    like_service: FeedPostLikeService = Depends(Provide[Container.feed_post_like_service]),
) -> LikeResponse:
    """게시물 좋아요 추가."""
    user_id: str = request.state.user_id
    try:
        like_count = await like_service.add_like(user_id=user_id, post_id=post_id)
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return LikeResponse(post_id=post_id, like_count=like_count)


# ──────────────────── 취소 ────────────────────

@router.delete("/posts/{post_id}/like")
@inject
async def remove_like(
    request: Request,
    post_id: str,
    like_service: FeedPostLikeService = Depends(Provide[Container.feed_post_like_service]),
) -> LikeResponse:
    """게시물 좋아요 취소."""
    user_id: str = request.state.user_id
    try:
        like_count = await like_service.remove_like(user_id=user_id, post_id=post_id)
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return LikeResponse(post_id=post_id, like_count=like_count)


# ──────────────────── 좋아요 누른 유저 목록 ────────────────────

@router.get("/posts/{post_id}/likes")
@inject
async def get_liked_users(
    request: Request,
    post_id: str,
    like_service: FeedPostLikeService = Depends(Provide[Container.feed_post_like_service]),
) -> LikedUsersResponse:
    """좋아요 유저 목록 — 최신순. 단일 JOIN 으로 닉네임/프로필 이미지 포함."""
    viewer_id: str = request.state.user_id
    try:
        users = await like_service.get_liked_users(
            viewer_id=viewer_id, post_id=post_id,
        )
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return LikedUsersResponse(
        post_id=post_id,
        users=[_to_liked_user_item(u) for u in users],
    )


# ──────────────────── 내부 유틸 ────────────────────

def _to_liked_user_item(user: LikedUserData) -> LikedUserItem:
    return LikedUserItem(
        user_id=user.user_id,
        user_name=user.user_name,
        profile_image_url=user.profile_image_url,
    )
