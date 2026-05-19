"""메시지 편집 / 삭제 REST 엔드포인트

방 관리(`/chat/rooms/*`) 와 별개로 `/chat/messages/{id}` 경로를 쓴다 — 방 id 를 몰라도
메시지 id 만으로 접근할 수 있게 하고, 클라가 검색/알림 링크에서 바로 진입하는 케이스도 고려.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from dependency_injector.wiring import Provide, inject

from app.domain.chat.service.message import MessageService
from app.domain.chat.schema.message import EditMessageBody, EditMessageResponse
from app.container import Container


router = APIRouter(prefix="/messages", tags=["채팅 - 메시지 편집/삭제"])


# ──────────────────── 편집 ────────────────────

@router.patch("/{message_id}")
@inject
async def edit_message(
    request: Request,
    message_id: str,
    body: EditMessageBody,
    service: MessageService = Depends(Provide[Container.message_service]),
) -> EditMessageResponse:
    """본인 메시지 5분 이내 편집. 편집 후 방 전체에 `message.updated` 발행."""
    user_id: str = request.state.user_id
    # REST 요청에는 WS session_id 가 없음 — fan-out 에서 본인 에코 스킵 대상 없음.
    editor_session_id = ""

    try:
        result = await service.edit_message(
            message_id=message_id,
            editor_user_id=user_id,
            editor_session_id=editor_session_id,
            new_content=body.content,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return EditMessageResponse(**result)


# ──────────────────── 삭제 (soft) ────────────────────

@router.delete("/{message_id}", status_code=204)
@inject
async def delete_message(
    request: Request,
    message_id: str,
    service: MessageService = Depends(Provide[Container.message_service]),
) -> None:
    """본인 메시지 OR 그룹방 creator 의 soft delete. 방 전체에 `message.deleted` 발행."""
    user_id: str = request.state.user_id
    deleter_session_id = ""

    try:
        await service.delete_message(
            message_id=message_id,
            deleter_user_id=user_id,
            deleter_session_id=deleter_session_id,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
