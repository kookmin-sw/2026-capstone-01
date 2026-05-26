"""인박스 라우터.

자동 읽음 처리는 첫 페이지(`cursor` 미지정) 진입 시에만 `mark_as_read=True` — 응답의
`is_read` 는 read 전 상태 그대로라 클라가 "방금 본 항목" 강조 가능.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from dependency_injector.wiring import Provide, inject

from app.schema.common import MessageResponse
from app.domain.notification.service.inbox import InboxService
from app.domain.notification.service.exception import InboxItemNotFoundError
from app.domain.notification.schema.inbox import (
    InboxItemResponse,
    InboxListResponse,
    UnreadCountResponse,
)
from app.domain.notification.dto.inbox import (
    InboxItemData,
    InboxListData,
)
from app.container import Container


router = APIRouter(prefix="/inbox", tags=["인박스"])


# ──────────────────── 목록 ────────────────────

@router.get("")
@inject
async def list_inbox(
    request: Request,
    cursor: Optional[str] = Query(
        None, description="다음 페이지 커서 (마지막 항목의 created_at ISO string)",
    ),
    service: InboxService = Depends(Provide[Container.inbox_service]),
) -> InboxListResponse:
    """display=true 항목 최신순 페이지네이션. 첫 페이지 진입 시 미읽음 자동 read 처리."""
    user_id: str = request.state.user_id
    try:
        result = await service.list_items(
            recipient_id=user_id,
            cursor=cursor,
            mark_as_read=(cursor is None),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _to_list_response(result)


# ──────────────────── 미읽음 카운트 ────────────────────

@router.get("/unread-count")
@inject
async def get_unread_count(
    request: Request,
    service: InboxService = Depends(Provide[Container.inbox_service]),
) -> UnreadCountResponse:
    """미읽음 카운트 — 999+ 캡."""
    user_id: str = request.state.user_id
    count = await service.count_unread(recipient_id=user_id)
    return UnreadCountResponse(unread_count=count)


# ──────────────────── X 버튼 (숨기기) ────────────────────

@router.patch("/{inbox_item_id}/hide")
@inject
async def hide_inbox_item(
    request: Request,
    inbox_item_id: str,
    service: InboxService = Depends(Provide[Container.inbox_service]),
) -> MessageResponse:
    """X 버튼 — display=False 토글. 본인 소유만."""
    user_id: str = request.state.user_id
    try:
        await service.hide_item(
            recipient_id=user_id, inbox_item_id=inbox_item_id,
        )
    except InboxItemNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return MessageResponse(message="인박스 항목이 숨겨졌습니다.")


# ──────────────────── 내부 유틸 ────────────────────

def _to_response(item: InboxItemData) -> InboxItemResponse:
    return InboxItemResponse(
        inbox_item_id=item.inbox_item_id,
        type=item.type,
        actor_id=item.actor_id,
        actor_name=item.actor_name,
        actor_profile_image_url=item.actor_profile_image_url,
        target_type=item.target_type,
        target_id=item.target_id,
        comment_id=item.comment_id,
        target_preview=item.target_preview,
        comment_preview=item.comment_preview,
        is_read=item.is_read,
        created_at=item.created_at,
    )


def _to_list_response(result: InboxListData) -> InboxListResponse:
    return InboxListResponse(
        items=[_to_response(i) for i in result.items],
        next_cursor=result.next_cursor,
    )
