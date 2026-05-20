"""타 유저 피드 조회 라우터.

타 유저 케이스는 service 가 PRIVATE 을 필터링하므로 응답엔 FRIENDS/PUBLIC 만 노출
(viewer=owner 면 PRIVATE 도 포함).
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from dependency_injector.wiring import Provide, inject

from app.domain.feed.service.feed_post import FeedPostService
from app.domain.feed.schema.feed_post import FeedPostResponse, FeedPostListResponse
from app.domain.feed.dto.feed_post import FeedPostData, FeedPostListData
from app.container import Container


router = APIRouter(tags=["타 유저 피드 조회"])


@router.get("/users/{user_id}")
@inject
async def get_user_feed(
    request: Request,
    user_id: str,
    cursor: Optional[str] = Query(None, description="다음 페이지 커서 (post_id)"),
    feed_service: FeedPostService = Depends(Provide[Container.feed_post_service]),
) -> FeedPostListResponse:
    """다른 유저 피드 — 친구/차단/visibility 결합 커서 페이지네이션.

    viewer=owner: 모든 visibility / 친구: FRIENDS+PUBLIC / 비친구: PUBLIC / 차단: 403.
    """
    viewer_id: str = request.state.user_id
    try:
        result = await feed_service.get_user_feed(
            viewer_id=viewer_id, owner_id=user_id, cursor=cursor,
        )
    except PermissionError as e:
        # FeedBlockedError 가 PermissionError 하위 — 단일 catch.
        raise HTTPException(status_code=403, detail=str(e))
    return _to_list_response(result)


# ──────────────────── 내부 유틸 ────────────────────

def _to_response(post: FeedPostData) -> FeedPostResponse:
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
