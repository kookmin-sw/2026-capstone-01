"""피드 게시물 댓글 서비스.

권한: 게시물을 볼 수 있는 viewer 만 작성/조회 (`access.load_viewable_post`).
삭제는 작성자 본인만 — owner 라도 댓글 삭제 불가 (MVP 단순화. owner 는 visibility 변경 또는
게시물 삭제로 통째 정리 가능).

빈 입력 정책: schema `min_length=1` 1차, `_normalize_content` (strip 후 빈) 2차, DB CHECK 가 마지막.
캡션과 달리 빈은 400 — 추가 액션에 빈 본문은 무의미.

작성자 프로필: repository 의 모든 read 가 `joinedload(user.detail)` → DTO 변환 시 lazy-load 없이 채움.
`create_comment` 는 INSERT 직후 reload (round-trip 1회 추가) — async session 의 lazy 차단으로
explicit reload 가 가장 명확.

인박스: create 는 트랜잭션 후 fan-out (RDB 커밋 후 Mongo insert — 롤백된 댓글의 인박스 발사 회피).
delete 는 cascade 안 함 (정책상 보존, deep link 404 + TTL 30일로 자연 정리).
본인→본인 댓글은 fan-out skip.
"""
from typing import Optional

from app.util.id_generator import generate_feed_post_comment_id
from app.domain.notification.service.inbox import InboxService
from app.domain.feed.service.exception import FeedPostCommentNotFoundError
from app.domain.feed.service.access import load_viewable_post
from app.domain.feed.repository.feed_post_comment import FeedPostCommentRepository, PAGE_SIZE
from app.domain.feed.model.feed_post_comment import FeedPostComment
from app.domain.feed.dto.feed_post_comment import (
    FeedPostCommentData,
    FeedPostCommentListData,
    CreateCommentResult,
)
from app.database.session import UnitOfWork, transactional
from app.core.logger import get_logger


logger = get_logger("feed.post.comment.service")


def _normalize_content(content: str) -> str:
    """strip 후 빈이면 ValueError. schema 가 못 잡는 공백만 입력을 차단."""
    stripped = content.strip()
    if not stripped:
        raise ValueError("댓글 내용이 비어 있습니다.")
    return stripped


class FeedPostCommentService:
    def __init__(self, uow: UnitOfWork, inbox_service: InboxService):
        self.uow = uow
        self.inbox_service = inbox_service


    async def create_comment(
        self,
        user_id: str,
        post_id: str,
        content: str,
    ) -> FeedPostCommentData:
        """댓글 작성. 트랜잭션 내 INSERT + reload, 트랜잭션 밖 인박스 fan-out (best-effort).

        Mongo 일시 장애로 인박스 누락되어도 사용자 응답은 정상.
        """
        result = await self._create_comment_tx(
            user_id=user_id, post_id=post_id, content=content,
        )
        if result.notify_recipient_id is not None:
            await self.inbox_service.notify_feed_comment(
                recipient_id=result.notify_recipient_id,
                actor_id=user_id,
                actor_name=result.dto.user_name,
                actor_profile_image_url=result.dto.profile_image_url,
                post_id=post_id,
                post_preview=result.notify_post_preview,
                comment_id=result.dto.comment_id,
                comment_content=result.dto.content,
            )
        return result.dto


    @transactional
    async def _create_comment_tx(
        self,
        *,
        user_id: str,
        post_id: str,
        content: str,
    ) -> CreateCommentResult:
        """가시성 검증 → INSERT → reload → fan-out payload.

        joinedload 로 dto 변환 시 닉네임/프로필 자동 채움. 본인→본인이면 recipient=None.
        """
        post = await load_viewable_post(self._session, viewer_id=user_id, post_id=post_id)
        normalized = _normalize_content(content)

        repo = FeedPostCommentRepository(self._session)
        comment = FeedPostComment(
            comment_id=generate_feed_post_comment_id(),
            post_id=post.post_id,
            user_id=user_id,
            content=normalized,
        )
        saved = await repo.save(comment)
        logger.info(
            "피드 댓글 작성 (user_id={}, post_id={}, comment_id={})",
            user_id, post.post_id, saved.comment_id,
        )
        loaded = await repo.find_by_id(saved.comment_id)
        dto = self._to_dto(loaded)

        if post.user_id == user_id:
            return CreateCommentResult(
                dto=dto,
                notify_recipient_id=None,
                notify_post_preview=None,
            )

        return CreateCommentResult(
            dto=dto,
            notify_recipient_id=post.user_id,
            notify_post_preview=post.thumbnail_small_url,
        )


    @transactional
    async def list_comments(
        self,
        viewer_id: str,
        post_id: str,
        cursor: Optional[str] = None,
    ) -> FeedPostCommentListData:
        """댓글 목록 (최신순 PAGE_SIZE). 가시성 검증 후 cursor 페이지네이션."""
        post = await load_viewable_post(self._session, viewer_id=viewer_id, post_id=post_id)
        repo = FeedPostCommentRepository(self._session)
        comments = await repo.find_by_post(post_id=post.post_id, cursor=cursor)
        next_cursor = comments[-1].comment_id if len(comments) == PAGE_SIZE else None
        return FeedPostCommentListData(
            comments=[self._to_dto(c) for c in comments],
            next_cursor=next_cursor,
        )


    @transactional
    async def delete_comment(
        self,
        user_id: str,
        post_id: str,
        comment_id: str,
    ) -> None:
        """댓글 삭제 — 작성자 본인만. 다른 post 의 comment_id 면 mismatch == not found 로 일원화."""
        repo = FeedPostCommentRepository(self._session)
        comment = await repo.find_by_id(comment_id)
        if comment is None or comment.post_id != post_id:
            raise FeedPostCommentNotFoundError("존재하지 않는 댓글입니다.")
        if comment.user_id != user_id:
            raise PermissionError("댓글에 대한 권한이 없습니다.")

        await repo.delete(comment)
        logger.info(
            "피드 댓글 삭제 (user_id={}, post_id={}, comment_id={})",
            user_id, post_id, comment_id,
        )


    @staticmethod
    def _to_dto(c: FeedPostComment) -> FeedPostCommentData:
        """FeedPostComment (with joinedload) → DTO. detail 결손 시 빈 문자열 / None fallback."""
        user = c.user
        detail = user.detail if user is not None else None
        return FeedPostCommentData(
            comment_id=c.comment_id,
            post_id=c.post_id,
            user_id=c.user_id,
            user_name=detail.user_name if detail is not None else "",
            profile_image_url=detail.profile_image_url if detail is not None else None,
            content=c.content,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
