"""피드 댓글 라우터."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from dependency_injector.wiring import Provide, inject

from app.schema.common import MessageResponse
from app.domain.feed.service.feed_post_comment import FeedPostCommentService
from app.domain.feed.service.exception import (
    FeedNotFoundError,
    FeedPostCommentNotFoundError,
)
from app.domain.feed.schema.feed_post_comment import (
    CommentListResponse,
    CommentResponse,
    CreateCommentRequest,
)
from app.domain.feed.dto.feed_post_comment import (
    FeedPostCommentData,
    FeedPostCommentListData,
)
from app.container import Container


router = APIRouter(tags=["피드 댓글"])


# ──────────────────── 작성 ────────────────────

@router.post("/posts/{post_id}/comments", status_code=201)
@inject
async def create_comment(
    request: Request,
    post_id: str,
    body: CreateCommentRequest,
    comment_service: FeedPostCommentService = Depends(
        Provide[Container.feed_post_comment_service]
    ),
) -> CommentResponse:
    """댓글 작성. 게시물을 볼 수 있어야 작성 가능."""
    user_id: str = request.state.user_id
    try:
        comment = await comment_service.create_comment(
            user_id=user_id, post_id=post_id, content=body.content,
        )
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _to_response(comment)


# ──────────────────── 목록 ────────────────────

@router.get("/posts/{post_id}/comments")
@inject
async def list_comments(
    request: Request,
    post_id: str,
    cursor: Optional[str] = Query(None, description="다음 페이지 커서 (comment_id)"),
    comment_service: FeedPostCommentService = Depends(
        Provide[Container.feed_post_comment_service]
    ),
) -> CommentListResponse:
    """댓글 목록 — 최신순 커서 페이지네이션. 게시물을 볼 수 있어야 조회 가능."""
    viewer_id: str = request.state.user_id
    try:
        result = await comment_service.list_comments(
            viewer_id=viewer_id, post_id=post_id, cursor=cursor,
        )
    except FeedNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return _to_list_response(result)


# ──────────────────── 삭제 ────────────────────

@router.delete("/posts/{post_id}/comments/{comment_id}")
@inject
async def delete_comment(
    request: Request,
    post_id: str,
    comment_id: str,
    comment_service: FeedPostCommentService = Depends(
        Provide[Container.feed_post_comment_service]
    ),
) -> MessageResponse:
    """댓글 삭제 — 작성자 본인만 (게시물 owner 라도 안 됨)."""
    user_id: str = request.state.user_id
    try:
        await comment_service.delete_comment(
            user_id=user_id, post_id=post_id, comment_id=comment_id,
        )
    except FeedPostCommentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return MessageResponse(message="댓글이 삭제되었습니다.")


# ──────────────────── 내부 유틸 ────────────────────

def _to_response(c: FeedPostCommentData) -> CommentResponse:
    return CommentResponse(
        comment_id=c.comment_id,
        post_id=c.post_id,
        user_id=c.user_id,
        user_name=c.user_name,
        profile_image_url=c.profile_image_url,
        content=c.content,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _to_list_response(result: FeedPostCommentListData) -> CommentListResponse:
    return CommentListResponse(
        comments=[_to_response(c) for c in result.comments],
        next_cursor=result.next_cursor,
    )
