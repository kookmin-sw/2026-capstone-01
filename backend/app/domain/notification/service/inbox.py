"""인박스 fan-out + 조회 / hide + cascade.

- stateless (Mongo 단독, RDB UoW 의존 없음). caller 가 actor 정보 / target preview 를 채워서 넘긴다.
- fan-out 은 RDB 트랜잭션 *밖* 에서 호출되어야 함 (caller 책임). `DuplicateKeyError` 는 멱등 skip,
  그 외는 로그만 + 응답 정상. Mongo 일시 장애로 1건 누락돼도 사용자 액션 응답은 정상.
- 본인→본인 항목 skip — 모든 fan-out 진입점에서 가드.
- 인박스는 mute 영향 없음 (mute 는 푸시 전용).

cascade:
- user_withdrawn: hard delete (recipient/actor 매칭).
- post_deleted  : `(target_type, target_id)` soft hide. 좋아요 *취소* 는 보존 정책과 비대칭 —
  원본 소멸 시 deep link 404 가 확정이라 stale 알림이 작성자 본인 인박스에 남는 UX 손해를 막는다.
"""
from typing import Optional
from pymongo.errors import DuplicateKeyError
from datetime import datetime, timezone
from bson.errors import InvalidId
from beanie import PydanticObjectId

from app.domain.notification.service.exception import InboxItemNotFoundError
from app.domain.notification.repository.inbox import (
    InboxRepository,
    PAGE_SIZE,
    UNREAD_COUNT_CAP,
)
from app.domain.notification.model.inbox import (
    InboxItem,
    InboxItemType,
    TargetType,
    COMMENT_PREVIEW_MAX_LENGTH,
)
from app.domain.notification.dto.inbox import (
    InboxItemData,
    InboxListData,
)
from app.core.logger import get_logger


logger = get_logger("inbox.service")


class InboxService:
    def __init__(self):
        self.repo = InboxRepository()


    async def notify_feed_like(
        self,
        *,
        recipient_id: str,
        actor_id: str,
        actor_name: str,
        actor_profile_image_url: Optional[str],
        post_id: str,
        post_preview: Optional[str],
    ) -> None:
        """피드 좋아요 fan-out. `uq_inbox_dedup` partial filter 로 display=true 중복은 멱등 skip."""
        if recipient_id == actor_id:
            return
        item = InboxItem(
            recipient_id=recipient_id,
            actor_id=actor_id,
            type=InboxItemType.FEED_LIKE,
            target_type=TargetType.FEED_POST,
            target_id=post_id,
            actor_name=actor_name,
            actor_profile_image_url=actor_profile_image_url,
            target_preview=post_preview,
        )
        await self._safe_insert(item)


    async def notify_feed_comment(
        self,
        *,
        recipient_id: str,
        actor_id: str,
        actor_name: str,
        actor_profile_image_url: Optional[str],
        post_id: str,
        post_preview: Optional[str],
        comment_id: str,
        comment_content: str,
    ) -> None:
        """피드 댓글 fan-out — `comment_id` 별 별도 항목 (묶음 없음). 본문은 snapshot 으로 truncate."""
        if recipient_id == actor_id:
            return
        item = InboxItem(
            recipient_id=recipient_id,
            actor_id=actor_id,
            type=InboxItemType.FEED_COMMENT,
            target_type=TargetType.FEED_POST,
            target_id=post_id,
            comment_id=comment_id,
            actor_name=actor_name,
            actor_profile_image_url=actor_profile_image_url,
            target_preview=post_preview,
            comment_preview=_truncate_comment(comment_content),
        )
        await self._safe_insert(item)


    async def notify_tripmate_like(
        self,
        *,
        recipient_id: str,
        actor_id: str,
        actor_name: str,
        actor_profile_image_url: Optional[str],
        post_id: str,
        post_preview: Optional[str],
    ) -> None:
        """트립메이트 좋아요 fan-out. `post_preview` 는 게시글 title."""
        if recipient_id == actor_id:
            return
        item = InboxItem(
            recipient_id=recipient_id,
            actor_id=actor_id,
            type=InboxItemType.TRIPMATE_LIKE,
            target_type=TargetType.TRIPMATE_POST,
            target_id=post_id,
            actor_name=actor_name,
            actor_profile_image_url=actor_profile_image_url,
            target_preview=post_preview,
        )
        await self._safe_insert(item)


    async def list_items(
        self,
        recipient_id: str,
        cursor: Optional[str] = None,
        mark_as_read: bool = False,
    ) -> InboxListData:
        """display=true 항목 최신순 페이지네이션. cursor 는 마지막 항목의 ISO created_at.

        `mark_as_read=True` 면 응답 dto 변환 *후* 미읽음 일괄 read 처리 → 응답의 `is_read` 는
        read 전 상태 유지 (클라가 "방금 본 항목" 강조 가능). 실패는 swallow (다음 진입에 재시도).
        """
        cursor_dt = None
        if cursor is not None:
            try:
                cursor_dt = datetime.fromisoformat(cursor)
            except ValueError:
                raise ValueError("cursor 형식이 올바르지 않습니다.") from None
            # naive datetime 방어 — 외부 클라가 tz 누락 ISO 를 보내면 UTC 가정. 서버 반환 cursor 는 항상 tz-aware.
            if cursor_dt.tzinfo is None:
                cursor_dt = cursor_dt.replace(tzinfo=timezone.utc)

        items = await self.repo.find_by_recipient(
            recipient_id=recipient_id, cursor=cursor_dt, limit=PAGE_SIZE,
        )
        has_more = len(items) > PAGE_SIZE
        items = items[:PAGE_SIZE]
        next_cursor = (
            items[-1].created_at.isoformat() if has_more and items else None
        )
        result = InboxListData(
            items=[self._to_dto(i) for i in items],
            next_cursor=next_cursor,
        )

        if mark_as_read:
            try:
                modified = await self.repo.mark_all_read(recipient_id)
                if modified > 0:
                    logger.info(
                        "인박스 자동 읽음 처리 (recipient_id={}, count={})",
                        recipient_id, modified,
                    )
            except Exception as e:
                logger.warning(
                    "인박스 자동 읽음 처리 실패 (recipient_id={}, error={})",
                    recipient_id, e,
                )

        return result


    async def count_unread(self, recipient_id: str) -> int:
        """미읽음 뱃지 — 999+ 캡."""
        raw = await self.repo.count_unread(recipient_id, cap=UNREAD_COUNT_CAP)
        return min(raw, UNREAD_COUNT_CAP)


    async def hide_item(
        self, recipient_id: str, inbox_item_id: str,
    ) -> None:
        """X 버튼 — 본인 소유만. 잘못된 id 형식 / 미존재 / 타인 소유 / 이미 hide 모두 동일 404."""
        try:
            oid = PydanticObjectId(inbox_item_id)
        except (InvalidId, TypeError, ValueError):
            raise InboxItemNotFoundError("존재하지 않는 인박스 항목입니다.") from None

        modified = await self.repo.hide(oid, recipient_id)
        if not modified:
            raise InboxItemNotFoundError("존재하지 않는 인박스 항목입니다.")
        logger.info("인박스 항목 hide (recipient_id={}, inbox_item_id={})", recipient_id, inbox_item_id)


    async def cascade_post_deleted(
        self, *, target_type: TargetType, target_id: str,
    ) -> int:
        """게시글 삭제 cascade — 해당 게시글의 모든 알림 soft hide.

        RDB 트랜잭션 *밖* 에서 호출 — RDB 롤백된 삭제에 대해 Mongo 가 먼저 숨기는 race 회피.
        실패해도 stale 항목은 deep link 404 + TTL 30일로 자연 정리.
        """
        try:
            modified = await self.repo.hide_by_target(target_type.value, target_id)
            if modified > 0:
                logger.info(
                    "인박스 cascade post_deleted (target_type={}, target_id={}, modified={})",
                    target_type.value, target_id, modified,
                )
            return modified
        except Exception as e:
            logger.warning(
                "인박스 cascade post_deleted 실패 (target_type={}, target_id={}, error={})",
                target_type.value, target_id, e,
            )
            return 0


    async def cascade_user_withdrawn(self, user_id: str) -> int:
        """유저 탈퇴 cascade — recipient/actor 매칭 hard delete. best-effort (실패 시 TTL 정리)."""
        try:
            deleted = await self.repo.delete_by_user(user_id)
            if deleted > 0:
                logger.info(
                    "인박스 cascade user_withdrawn (user_id={}, deleted={})",
                    user_id, deleted,
                )
            return deleted
        except Exception as e:
            logger.warning(
                "인박스 cascade user_withdrawn 실패 (user_id={}, error={})",
                user_id, e,
            )
            return 0


    async def _safe_insert(self, item: InboxItem) -> None:
        """fan-out 공통 insert — `DuplicateKeyError` 멱등 skip, 그 외는 로그만 + 응답 정상."""
        try:
            await self.repo.insert(item)
        except DuplicateKeyError:
            return
        except Exception as e:
            logger.warning(
                "인박스 fan-out 실패 (type={}, recipient_id={}, target_id={}, error={})",
                item.type.value, item.recipient_id, item.target_id, e,
            )


    @staticmethod
    def _to_dto(item: InboxItem) -> InboxItemData:
        return InboxItemData(
            inbox_item_id=str(item.id),
            type=item.type,
            actor_id=item.actor_id,
            actor_name=item.actor_name,
            actor_profile_image_url=item.actor_profile_image_url,
            target_type=item.target_type,
            target_id=item.target_id,
            comment_id=item.comment_id,
            target_preview=item.target_preview,
            comment_preview=item.comment_preview,
            is_read=item.read_at is not None,
            created_at=item.created_at,
        )


def _truncate_comment(content: str) -> str:
    """댓글 snapshot — `COMMENT_PREVIEW_MAX_LENGTH` 자로 자르고 길면 ellipsis."""
    if len(content) <= COMMENT_PREVIEW_MAX_LENGTH:
        return content
    return content[:COMMENT_PREVIEW_MAX_LENGTH] + "…"
