"""피드 팝업 라우터 — 다른 유저 프로필 미리보기 (프로필 + 최근 9개 피드).

next_cursor 미제공 — 더보기는 클라가 `GET /feed/users/{user_id}` 로 분기.
"""
from fastapi import APIRouter, HTTPException, Request, Depends
from dependency_injector.wiring import Provide, inject

from app.domain.feed.service.feed_popup import FeedPopupService
from app.domain.feed.service.exception import PopupTargetNotFoundError
from app.domain.feed.schema.feed_post import FeedPostResponse
from app.domain.feed.schema.feed_popup import FeedPopupResponse, PopupFeedSection
from app.domain.feed.dto.feed_post import FeedPostData
from app.domain.feed.dto.feed_popup import FeedPopupData
from app.container import Container


router = APIRouter(tags=["피드 팝업"])


@router.get("/popup/{user_id}")
@inject
async def get_popup(
    request: Request,
    user_id: str,
    popup_service: FeedPopupService = Depends(Provide[Container.feed_popup_service]),
) -> FeedPopupResponse:
    """프로필 5종 + 최근 9개 피드.

    - viewer=owner: 모든 visibility / 친구: FRIENDS+PUBLIC / 비친구: PUBLIC / 차단: 403 / 미존재·미가입: 404
    """
    viewer_id: str = request.state.user_id
    try:
        popup = await popup_service.get_popup(
            viewer_id=viewer_id, owner_id=user_id,
        )
    except PopupTargetNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        # FeedBlockedError 가 PermissionError 하위라 단일 catch.
        raise HTTPException(status_code=403, detail=str(e))

    return _to_response(popup)


# ──────────────────── 내부 유틸 ────────────────────

def _to_response(popup: FeedPopupData) -> FeedPopupResponse:
    return FeedPopupResponse(
        user_id=popup.user_id,
        user_name=popup.user_name,
        nationality=popup.nationality,
        travel_styles=popup.travel_styles,
        profile_image_url=popup.profile_image_url,
        feed=PopupFeedSection(
            items=[_to_feed_item(p) for p in popup.feed_items],
        ),
    )


def _to_feed_item(p: FeedPostData) -> FeedPostResponse:
    return FeedPostResponse(
        post_id=p.post_id,
        user_id=p.user_id,
        visibility=p.visibility,
        caption=p.caption,
        original_url=p.original_url,
        thumbnail_small_url=p.thumbnail_small_url,
        thumbnail_medium_url=p.thumbnail_medium_url,
        like_count=p.like_count,
        comment_count=p.comment_count,
        is_liked=p.is_liked,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )
