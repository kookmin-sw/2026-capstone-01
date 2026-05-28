from typing import List

from app.domain.tripmate.repository.tripmate_post_like import TripmatePostLikeRepository
from app.domain.tripmate.repository.tripmate_post import TripmatePostRepository
from app.domain.tripmate.model.tripmate_post_like import TripmatePostLike
from app.domain.tripmate.dto.tripmate_post_like import AddLikePayload
from app.domain.notification.service.inbox import InboxService
from app.domain.auth.repository.user_detail_inform import UserDetailInformRepository
from app.database.session import UnitOfWork, transactional
from app.core.logger import get_logger


logger = get_logger("tripmate.post.like.service")


class TripmatePostLikeService:
    def __init__(self, uow: UnitOfWork, inbox_service: InboxService):
        self.uow = uow
        self.inbox_service = inbox_service


    # ──────────────────── 좋아요 누른 유저 조회 ────────────────────

    @transactional
    async def get_liked_user_ids(self, post_id: str) -> List[str]:
        """
        게시글에 좋아요 누른 유저 ID 목록 조회

        1. 게시글 존재 검증
        2. 좋아요 누른 유저 ID 목록 반환 (최신순)
        """
        post_repo = TripmatePostRepository(self._session)
        like_repo = TripmatePostLikeRepository(self._session)

        post = await post_repo.find_by_id(post_id)
        if post is None:
            raise ValueError("존재하지 않는 게시글입니다.")

        return await like_repo.find_user_ids_by_post(post_id)


    # ──────────────────── 좋아요 추가 ────────────────────

    async def add_like(self, user_id: str, post_id: str) -> int:
        """좋아요 추가 — 트랜잭션 내 INSERT 후, 트랜잭션 밖에서 인박스 fan-out (best-effort).

        본인→본인 좋아요는 fan-out skip (caller 가드 + InboxService 가드 이중).
        Mongo 일시 장애로 인박스 누락되어도 사용자 응답 정상.
        """
        payload = await self._add_like_tx(user_id=user_id, post_id=post_id)
        if payload.recipient_id != user_id:
            await self.inbox_service.notify_tripmate_like(
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
        """좋아요 추가 트랜잭션 — 게시글 검증 → 중복 검사 → INSERT → count → payload 합성.

        본인이면 detail fetch skip (outer 가 어차피 fan-out 안 함).
        """
        post_repo = TripmatePostRepository(self._session)
        like_repo = TripmatePostLikeRepository(self._session)

        post = await post_repo.find_by_id(post_id)
        if post is None:
            raise ValueError("존재하지 않는 게시글입니다.")

        existing = await like_repo.find_by_user_and_post(user_id, post_id)
        if existing is not None:
            raise ValueError("이미 좋아요를 누른 게시글입니다.")

        like = TripmatePostLike(user_id=user_id, post_id=post_id)
        await like_repo.save(like)
        like_count = await like_repo.count_by_post(post_id)

        # 본인→본인 — outer 가 fan-out skip
        if post.user_id == user_id:
            return AddLikePayload(
                like_count=like_count,
                recipient_id=post.user_id,
                actor_name="",
                actor_profile_image_url=None,
                post_preview=None,
            )

        # 외부 actor — 같은 트랜잭션 안에서 detail fetch (round-trip 1회).
        detail_repo = UserDetailInformRepository(self._session)
        detail = await detail_repo.find_by_user_id(user_id)
        return AddLikePayload(
            like_count=like_count,
            recipient_id=post.user_id,
            actor_name=detail.user_name if detail is not None else "",
            actor_profile_image_url=detail.profile_image_url if detail is not None else None,
            post_preview=post.title,
        )


    # ──────────────────── 좋아요 삭제 ────────────────────

    @transactional
    async def remove_like(self, user_id: str, post_id: str) -> int:
        """
        게시글 좋아요 취소

        1. 좋아요 존재 검증
        2. 좋아요 삭제 후 현재 좋아요 수 반환
        """
        like_repo = TripmatePostLikeRepository(self._session)

        existing = await like_repo.find_by_user_and_post(user_id, post_id)
        if existing is None:
            raise ValueError("좋아요를 누르지 않은 게시글입니다.")

        await like_repo.delete_by_user_and_post(user_id, post_id)

        return await like_repo.count_by_post(post_id)
