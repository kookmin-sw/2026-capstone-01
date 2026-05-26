from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from dependency_injector.wiring import Provide, inject

from app.domain.friend.service.search_history import FriendSearchHistoryService
from app.domain.friend.service.search import FriendSearchService
from app.domain.friend.schema.search import (
    FriendSearchItemResponse,
    FriendSearchListResponse,
)
from app.core.logger import get_logger
from app.container import Container


router = APIRouter(prefix="/search", tags=["친구 추가 화면 유저 검색"])
logger = get_logger("friend.search")


@router.get("")
@inject
async def search_users(
    request: Request,
    keyword: str = Query(..., min_length=1, description="검색 키워드 (user_name / user_id 부분일치)"),
    cursor: Optional[str] = Query(None, description="다음 페이지 커서 (user_id)"),
    service: FriendSearchService = Depends(Provide[Container.friend_search_service]),
    search_history_service: FriendSearchHistoryService = Depends(Provide[Container.friend_search_history_service]),
) -> FriendSearchListResponse:
    """이름 또는 user_id 로 친구 추가 후보 유저 검색 (30개씩 커서 페이지네이션)."""
    viewer_id: str = request.state.user_id

    # 키워드 정규화 — save_search 와 service.search 가 동일한 normalized 값을 보도록
    # router 단에서 한 번만 strip → 공백만 입력된 경우 history 오염 / 무의미한 search 호출을 차단
    keyword = keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="검색어를 입력해주세요.")

    # 검색 기록 저장은 첫 페이지(cursor 없음)에서만 — 페이지네이션 추가 호출이 동일 키워드를
    # 매번 upsert 해 불필요한 Mongo write 가 누적되는 것을 차단.
    # best-effort: Mongo 장애 시에도 검색 자체는 계속 진행
    if cursor is None:
        try:
            await search_history_service.save_search(user_id=viewer_id, search_name=keyword)
        except Exception:
            logger.warning("검색 기록 저장 실패: user_id={}, keyword={}", viewer_id, keyword)

    try:
        result = await service.search(viewer_id=viewer_id, keyword=keyword, cursor=cursor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _to_list_response(result)


# ──────────────────── 내부 유틸 ────────────────────

def _to_item_response(dto) -> FriendSearchItemResponse:
    return FriendSearchItemResponse(
        user_id=dto.user_id,
        user_name=dto.user_name,
        profile_image_url=dto.profile_image_url,
        nationality=dto.nationality,
        travel_styles=dto.travel_styles,
        friendship_status=dto.friendship_status,
        is_requester=dto.is_requester,
        i_blocked_peer=dto.i_blocked_peer,
    )


def _to_list_response(dto) -> FriendSearchListResponse:
    return FriendSearchListResponse(
        items=[_to_item_response(item) for item in dto.items],
        next_cursor=dto.next_cursor,
    )
