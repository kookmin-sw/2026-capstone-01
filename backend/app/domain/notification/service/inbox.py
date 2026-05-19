"""인박스 서비스 — fan-out 진입점 + 인박스 조회 / hide + cascade.

설계:
    - **stateless** — RDB session 안 쓰고 Mongo (beanie) 단독. UoW 의존성 없음.
      caller (feed/tripmate service) 가 actor 정보 (닉네임/프로필 이미지) 와 target
      preview 를 채워서 fan-out 메서드에 넘긴다 — service 는 단순 insert 에 집중.
    - **fan-out best-effort** — RDB 트랜잭션 *밖* 에서 호출되어야 함 (caller 책임).
      `DuplicateKeyError` 는 멱등 skip, 그 외 예외는 로그만 + 응답 정상. Mongo 일시 장애로
      항목 1건 누락되어도 사용자 액션(좋아요/댓글) 응답에는 영향 없음.
    - **본인→본인 항목 skip** — `recipient_id == actor_id` 는 모든 fan-out 진입점에서 가드.
    - **mute 분리** — 인박스는 mute 영향 없음. 푸시(FCM) 만 mute 가드 적용.

API 매핑:
    notify_feed_like     ← feed_post_like.add_like
    notify_feed_comment  ← feed_post_comment.create_comment
    notify_tripmate_like ← tripmate_post_like.add_like

cascade 호출 매핑:
    cascade_user_withdrawn   ← withdraw_purge worker (유저 자체가 사라져 항목 의미 소멸)
    cascade_post_deleted     ← feed_post / tripmate_post `delete_post` (트랜잭션 커밋 후)

게시글 삭제 cascade 정책:
    - `(target_type, target_id)` 매칭 항목 일괄 soft hide (`display=False`). 한 게시글의
      좋아요·댓글 알림이 모두 인박스에서 사라진다 (TTL 30일로 hard delete).
    - 좋아요 *취소* 시엔 항목 그대로 보존 — "이벤트 발생 사실의 기록" 이라는 인박스 모델
      철학과 비대칭. 게시글 *삭제* 는 원본 자체 소멸이라 deep link 404 가 확정 → 클릭할
      가치 없는 stale 알림이 작성자 본인 인박스에 쌓이는 UX 손해를 막는다.
    - 댓글 단건 삭제는 cascade 안 함 (현 정책 — 사용자 요청 범위 밖).
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


    # ──────────────────── Fan-out (피드 좋아요) ────────────────────

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
        """피드 좋아요 인박스 fan-out — RDB 트랜잭션 밖에서 호출.

        본인→본인 좋아요는 skip. `uq_inbox_dedup` 으로 같은 (recipient, actor,
        FEED_LIKE, post_id) 의 display=true 항목이 이미 있으면 멱등 skip.
        """
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


    # ──────────────────── Fan-out (피드 댓글) ────────────────────

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
        """피드 댓글 인박스 fan-out — `comment_id` 마다 별도 항목 (1:1, 묶음 없음).

        본문은 `COMMENT_PREVIEW_MAX_LENGTH` 자로 잘라 snapshot. `comment_id` 가 매번
        달라 unique 충돌 안 함 — 같은 사람이 여러 댓글 달면 매번 항목.
        """
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


    # ──────────────────── Fan-out (트립메이트 좋아요) ────────────────────

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
        """트립메이트 좋아요 인박스 fan-out. `post_preview` 는 게시글 title 전달 권장."""
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


    # ──────────────────── 인박스 조회 ────────────────────

    async def list_items(
        self,
        recipient_id: str,
        cursor: Optional[str] = None,
        mark_as_read: bool = False,
    ) -> InboxListData:
        """인박스 — display=true 만 시간 역순 페이지네이션.

        cursor 는 ISO 8601 datetime string (마지막 항목의 `created_at`). 잘못된 형식은
        `ValueError` 로 router 에서 400.

        `mark_as_read=True` 면 응답 dto 변환 *후* 미읽음 일괄 읽음 처리 (router 가 첫
        페이지 진입 시점에만 True 로 호출). 응답의 `is_read` 는 read 전 상태 (false) 그대로
        유지하여 클라가 "방금 본 항목" 시각 강조 가능 — DB 는 호출 종료 시점에 read_at
        채워진 상태. Mongo 일시 장애는 swallow (다음 진입에 자연 재시도).
        """
        cursor_dt = None
        if cursor is not None:
            try:
                cursor_dt = datetime.fromisoformat(cursor)
            except ValueError:
                raise ValueError("cursor 형식이 올바르지 않습니다.") from None
            # naive datetime 방어 — 외부 클라가 tz 누락 ISO 를 보낸 경우 UTC 로 가정.
            # 서버 반환 next_cursor 는 항상 tz-aware (created_at = UTC) 라 정상 클라엔 영향 없음.
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
            # dto 변환 후에 update — 응답 is_read 는 read 전 상태 유지.
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
        """미읽음 뱃지 카운트 — 999+ 캡 적용된 값 반환."""
        raw = await self.repo.count_unread(recipient_id, cap=UNREAD_COUNT_CAP)
        return min(raw, UNREAD_COUNT_CAP)


    # ──────────────────── X 버튼 ────────────────────

    async def hide_item(
        self, recipient_id: str, inbox_item_id: str,
    ) -> None:
        """인박스 항목 숨기기 — 본인 소유만. atomic update 로 권한 검증.

        잘못된 ID 형식 / 미존재 / 다른 유저 소유 / 이미 hide 된 항목 모두
        `InboxItemNotFoundError` 로 일원화 (정보 누출 회피).
        """
        try:
            oid = PydanticObjectId(inbox_item_id)
        except (InvalidId, TypeError, ValueError):
            raise InboxItemNotFoundError("존재하지 않는 인박스 항목입니다.") from None

        modified = await self.repo.hide(oid, recipient_id)
        if not modified:
            raise InboxItemNotFoundError("존재하지 않는 인박스 항목입니다.")
        logger.info("인박스 항목 hide (recipient_id={}, inbox_item_id={})", recipient_id, inbox_item_id)


    # ──────────────────── Cascade (게시글 삭제 — soft hide) ────────────────────

    async def cascade_post_deleted(
        self, *, target_type: TargetType, target_id: str,
    ) -> int:
        """게시글 삭제 cascade — 해당 게시글의 모든 알림 (LIKE/COMMENT) soft hide.

        RDB 트랜잭션 *밖* 에서 호출되어야 함 (caller 책임). RDB 롤백된 삭제에 대해
        Mongo 항목을 미리 숨기는 race 회피 — fan-out insert 와 동일 contract.
        실패 시 stale 항목은 deep link 404 + TTL 30일로 자연 정리.

        권한 검증은 caller (feed/tripmate `delete_post`) 가 본인 소유 게시글로 이미
        제한한 상태 — 본 메서드는 단순 일괄 update.
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


    # ──────────────────── Cascade (유저 탈퇴만) ────────────────────

    async def cascade_user_withdrawn(self, user_id: str) -> int:
        """유저 탈퇴 cascade — recipient/actor 어느 쪽이든 매칭되는 항목 hard delete. best-effort.

        실패 시 stale 잔존 → withdraw_purge worker 가 재시도되거나 TTL 30일로 자연 정리.
        """
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


    # ──────────────────── 내부 유틸 ────────────────────

    async def _safe_insert(self, item: InboxItem) -> None:
        """fan-out 공통 insert — DuplicateKeyError 멱등 skip, 그 외는 로그만 + 응답 정상.

        RDB 트랜잭션과 분리되어 best-effort 보장. Mongo 일시 장애 시 항목 1건 누락 가능 —
        outbox 패턴은 Phase 2.
        """
        try:
            await self.repo.insert(item)
        except DuplicateKeyError:
            # 같은 (recipient, actor, type, target, comment) 의 display=true 항목 이미 존재 — 멱등
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
    """댓글 본문 snapshot — `COMMENT_PREVIEW_MAX_LENGTH` 자로 자르고 길면 ellipsis."""
    if len(content) <= COMMENT_PREVIEW_MAX_LENGTH:
        return content
    return content[:COMMENT_PREVIEW_MAX_LENGTH] + "…"
