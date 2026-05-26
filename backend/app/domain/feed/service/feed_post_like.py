"""피드 게시물 좋아요 서비스.

권한: 모든 진입점이 게시물을 볼 수 있는지 먼저 검증 (`access.load_viewable_post`).
차단 → 403, visibility 미충족 → 404. 본인 글에 본인 좋아요는 허용 (인스타와 동일).

중복/미존재: add 이미 누름 → 400, remove 안 누른 상태 → 400 (idempotent 안 함).

Race 처리: 동시 클릭으로 양쪽 `find` None 통과 후 INSERT 가 PK 충돌하면 동일 메시지의
`ValueError` 로 변환 — 의미상 "이미 좋아요" 와 동치. SQLAlchemy 의존성을 라우터로 누출시키지 않음.
변환 직후 함수 종료 → 같은 session 의 PendingRollbackError 위험 없음.

인박스 (`add_like` 전용): 트랜잭션 분리 — RDB 커밋 후 Mongo fan-out. 본인→본인은 skip
(caller 가드 + InboxService 가드 이중).
"""
from sqlalchemy.exc import IntegrityError

from app.domain.notification.service.inbox import InboxService
from app.domain.feed.service.access import load_viewable_post
from app.domain.feed.repository.feed_post_like import FeedPostLikeRepository
from app.domain.feed.model.feed_post_like import FeedPostLike
from app.domain.feed.dto.feed_post_like import AddLikePayload, LikedUserData
from app.domain.auth.repository.user_detail_inform import UserDetailInformRepository
from app.database.session import UnitOfWork, transactional
from app.core.logger import get_logger


logger = get_logger("feed.post.like.service")


class FeedPostLikeService:
    def __init__(self, uow: UnitOfWork, inbox_service: InboxService):
        self.uow = uow
        self.inbox_service = inbox_service


    async def add_like(self, user_id: str, post_id: str) -> int:
        """좋아요 추가. 트랜잭션 내 INSERT, 트랜잭션 밖 인박스 fan-out (best-effort)."""
        payload = await self._add_like_tx(user_id=user_id, post_id=post_id)
        if payload.recipient_id != user_id:
            await self.inbox_service.notify_feed_like(
                recipient_id=payload.recipient_id,
                actor_id=user_id,
                actor_name=payload.actor_name,
                actor_profile_image_url=payload.actor_profile_image_url,
                post_id=post_id,
                post_preview=payload.post_preview,
            )
        return payload.like_count


    @transactional
    async def _add_like_tx(self, *, user_id: str, post_id: str) -> AddLikePayload:
        """가시성 검증 → 중복 검사 → INSERT → count → fan-out payload.

        race 시 IntegrityError → "이미 좋아요" 메시지로 일원화 (모듈 docstring 참조).
        본인→본인이면 detail fetch skip — outer 가 어차피 fan-out 안 함.
        """
        post = await load_viewable_post(self._session, viewer_id=user_id, post_id=post_id)
        like_repo = FeedPostLikeRepository(self._session)

        existing = await like_repo.find_by_user_and_post(user_id, post.post_id)
        if existing is not None:
            raise ValueError("이미 좋아요를 누른 게시물입니다.")

        try:
            await like_repo.save(FeedPostLike(user_id=user_id, post_id=post.post_id))
        except IntegrityError:
            raise ValueError("이미 좋아요를 누른 게시물입니다.") from None
        like_count = await like_repo.count_by_post(post.post_id)
        logger.info("피드 좋아요 추가 (user_id={}, post_id={})", user_id, post.post_id)

        if post.user_id == user_id:
            return AddLikePayload(
                like_count=like_count,
                recipient_id=post.user_id,
                actor_name="",
                actor_profile_image_url=None,
                post_preview=None,
            )

        detail_repo = UserDetailInformRepository(self._session)
        detail = await detail_repo.find_by_user_id(user_id)
        return AddLikePayload(
            like_count=like_count,
            recipient_id=post.user_id,
            actor_name=detail.user_name if detail is not None else "",
            actor_profile_image_url=detail.profile_image_url if detail is not None else None,
            post_preview=post.thumbnail_small_url,
        )


    @transactional
    async def remove_like(self, user_id: str, post_id: str) -> int:
        """좋아요 취소 — 가시성 재검증 후 DELETE. owner 가 PRIVATE 로 바꾸면 취소도 거절."""
        post = await load_viewable_post(self._session, viewer_id=user_id, post_id=post_id)
        like_repo = FeedPostLikeRepository(self._session)

        existing = await like_repo.find_by_user_and_post(user_id, post.post_id)
        if existing is None:
            raise ValueError("좋아요를 누르지 않은 게시물입니다.")

        await like_repo.delete_by_user_and_post(user_id, post.post_id)
        like_count = await like_repo.count_by_post(post.post_id)
        logger.info("피드 좋아요 취소 (user_id={}, post_id={})", user_id, post.post_id)
        return like_count


    @transactional
    async def get_liked_users(
        self, viewer_id: str, post_id: str,
    ) -> list[LikedUserData]:
        """좋아요 누른 유저 목록 — 가시성 검증 후 단일 JOIN 쿼리로 프로필 포함 일괄 반환 (N+1 회피)."""
        post = await load_viewable_post(self._session, viewer_id=viewer_id, post_id=post_id)
        like_repo = FeedPostLikeRepository(self._session)
        likes = await like_repo.find_with_user_by_post(post.post_id)
        return [self._to_liked_user_dto(like) for like in likes]


    @staticmethod
    def _to_liked_user_dto(like: FeedPostLike) -> LikedUserData:
        """detail 결손 시 빈 문자열 / None fallback."""
        user = like.user
        detail = user.detail if user is not None else None
        return LikedUserData(
            user_id=like.user_id,
            user_name=detail.user_name if detail is not None else "",
            profile_image_url=detail.profile_image_url if detail is not None else None,
        )
