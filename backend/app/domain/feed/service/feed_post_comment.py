"""피드 게시물 댓글 서비스.

권한 정책:
    - 작성 / 목록 조회: 게시물을 볼 수 있는 viewer 만 (`access.load_viewable_post`).
      차단 → 403, visibility 미충족 → 404.
    - 삭제: 작성자 본인만 (게시물 owner 라도 안 됨 — MVP 단순화. owner 는 visibility 변경
      또는 게시물 삭제로 댓글 통째 정리 가능).

본인 fast-path: 본인 글에 본인이 댓글 가능.

댓글 빈 입력 정책 (캡션과 의도적 차이):
    - 캡션: 빈 → None 정규화 (없음 의미)
    - 댓글: 빈 → 400 (추가 액션이라 빈 본문 무의미). schema 의 `min_length=1` 1차 차단,
      서비스의 `_normalize_content` (strip 후 빈) 2차 차단, DB CHECK 가 마지막 방어선.

작성자 프로필 (user_name / profile_image_url) 응답 포함:
    - repository 의 모든 read (`find_by_id` / `find_by_post`) 가 `joinedload(user.detail)`
      로 단일 JOIN 쿼리 → DTO 변환 시 lazy-load 없이 닉네임/이미지 채움.
    - `create_comment` 는 INSERT 직후 `find_by_id(saved.comment_id)` 로 reload (round-trip
      1회 추가) — async session 에서 relationship lazy-load 가 막혀 있어 explicit reload
      가 가장 명확한 패턴. 동일 트랜잭션의 read-your-own-writes 보장.

인박스 통합:
    - `create_comment`: 트랜잭션 분리 (`_create_comment_tx` → outer). RDB 커밋 후 fan-out
      best-effort. dto 의 user_name/profile 이 그대로 인박스 snapshot 으로 사용 (joinedload
      덕에 추가 fetch 불필요).
    - `delete_comment`: 인박스 cascade 안 함 — 좋아요 취소 인박스 보존 정책과 대칭. stale 댓글
      항목은 deep link 404 + TTL 30일로 자연 정리.
    - 본인→본인 댓글은 fan-out skip (caller 가드 + InboxService 가드).
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
    """댓글 본문 정규화 — strip 후 검증. 빈 문자열 → ValueError (400).

    schema 의 `min_length=1` 가 길이 1 이상은 통과시키지만 공백만 ("   ") 은 안 막음.
    이를 strip 으로 잡고, 그 외엔 strip 결과를 그대로 저장 — 의미 없는 양끝 공백 제거.
    """
    stripped = content.strip()
    if not stripped:
        raise ValueError("댓글 내용이 비어 있습니다.")
    return stripped


class FeedPostCommentService:
    def __init__(self, uow: UnitOfWork, inbox_service: InboxService):
        self.uow = uow
        self.inbox_service = inbox_service


    # ──────────────────── 작성 ────────────────────

    async def create_comment(
        self,
        user_id: str,
        post_id: str,
        content: str,
    ) -> FeedPostCommentData:
        """댓글 작성 — 트랜잭션 내 INSERT + reload, 트랜잭션 밖에서 인박스 fan-out (best-effort).

        본인→본인 댓글은 fan-out skip. Mongo 일시 장애 시 인박스 누락되어도 사용자 응답 정상.
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
        """댓글 작성 트랜잭션 — 가시성 검증 → INSERT → reload → fan-out payload 합성.

        joinedload(user.detail) 로 dto 변환 시 닉네임/프로필 자동 채움 → 별도 detail fetch
        불필요. 본인→본인이면 `notify_recipient_id=None` 으로 outer 에서 skip.
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
        # joinedload 포함 reload — user.detail 까지 같은 SELECT 로 채움
        loaded = await repo.find_by_id(saved.comment_id)
        dto = self._to_dto(loaded)

        # 본인→본인 — outer 가 fan-out skip
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


    # ──────────────────── 목록 ────────────────────

    @transactional
    async def list_comments(
        self,
        viewer_id: str,
        post_id: str,
        cursor: Optional[str] = None,
    ) -> FeedPostCommentListData:
        """댓글 목록 — 최신순 PAGE_SIZE. 가시성 검증 후 cursor 페이지네이션."""
        post = await load_viewable_post(self._session, viewer_id=viewer_id, post_id=post_id)
        repo = FeedPostCommentRepository(self._session)
        comments = await repo.find_by_post(post_id=post.post_id, cursor=cursor)
        next_cursor = comments[-1].comment_id if len(comments) == PAGE_SIZE else None
        return FeedPostCommentListData(
            comments=[self._to_dto(c) for c in comments],
            next_cursor=next_cursor,
        )


    # ──────────────────── 삭제 ────────────────────

    @transactional
    async def delete_comment(
        self,
        user_id: str,
        post_id: str,
        comment_id: str,
    ) -> None:
        """댓글 삭제 — 작성자 본인만. 알림은 cascade 안 함 (정책상 보존).

        post_id 도 받아 path 일관성 + comment ↔ post 매칭 검증. 다른 post 의 comment_id 가
        넘어오면 `FeedPostCommentNotFoundError` (mismatch == not found 로 일원화).
        """
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


    # ──────────────────── 내부 유틸 ────────────────────

    @staticmethod
    def _to_dto(c: FeedPostComment) -> FeedPostCommentData:
        """FeedPostComment (with joinedload user.detail) → FeedPostCommentData.

        FK CASCADE 로 user 결손은 발생 안 하지만 (comment 가 함께 삭제됨), detail 결손은
        회원가입 미완료 등 비정상 상태에서 가능 — 빈 문자열 / None fallback (chat / like
        도메인의 동일 패턴).
        """
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
