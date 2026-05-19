"""피드 게시물 좋아요 서비스.

권한 정책:
    - 모든 진입점 (`add_like` / `remove_like` / `get_liked_users`) 이 게시물을 볼 수
      있는지 먼저 검증 — `access.load_viewable_post`. 보이지 않는 글에 좋아요 시도 시 거절.
    - 차단 관계 → 403 (FeedBlockedError)
    - visibility 미충족 (PRIVATE / FRIENDS-only 비친구) → 404 (FeedNotFoundError)
    - 본인 글에 본인이 좋아요는 허용 (인스타도 가능). 차단/visibility 모두 fast-path 통과.

중복 / 미존재 정책:
    - `add_like`: 이미 좋아요 → 400 (tripmate 패턴, idempotent 안 함)
    - `remove_like`: 안 누른 상태 → 400

동시성 (race) 정책:
    - 같은 (user, post) 를 거의 동시에 두 번 클릭해 양쪽 모두 `find_by_user_and_post` 의
      None 분기를 통과한 뒤 늦게 도착한 INSERT 가 composite PK 충돌로 `IntegrityError` 를
      내는 케이스가 있다. 의미상 "이미 좋아요 누름" 과 동치 → 동일 메시지의 `ValueError`
      로 일원화 (라우터 400). 클라이언트는 일반 중복 케이스와 같은 코드로 처리 가능.
    - SQLAlchemy 의존성을 라우터로 누출시키지 않기 위해 본 모듈 (service) 에서 변환.
      변환 직후 함수에서 빠져나오므로 같은 session 의 추가 쿼리 (PendingRollbackError 위험)
      는 없고, `@transactional` 의 __aexit__ 가 rollback 실행 → 트랜잭션 정합 보장.

인박스 fan-out (`add_like` 전용):
    - `_add_like_tx` (트랜잭션 내) → outer `add_like` (트랜잭션 밖) 에서 fan-out 호출.
      RDB 커밋 후 Mongo insert → RDB 롤백된 좋아요에 대한 인박스 항목 발사 회피.
    - 본인→본인 좋아요는 caller 가드로 Mongo 호출 자체 skip (InboxService 도 가드,
      이중 안전망).
    - actor 닉네임/프로필은 같은 트랜잭션 안에서 fetch — payload 합성 후 outer 에 넘김.

응답: `(post_id, like_count)` — 클라이언트가 액션 직후 UI 즉시 갱신 가능.
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


    # ──────────────────── 추가 ────────────────────

    async def add_like(self, user_id: str, post_id: str) -> int:
        """좋아요 추가 — 트랜잭션 내 INSERT 후, 트랜잭션 밖에서 인박스 fan-out (best-effort).

        본인→본인 좋아요는 fan-out skip (caller 가드 + InboxService 가드 이중).
        Mongo 일시 장애로 인박스 누락되어도 사용자 응답은 정상 (`_safe_insert` swallow).
        """
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
        """좋아요 추가 트랜잭션 — 가시성 검증 → INSERT → count → fan-out payload 합성.

        흐름:
            1. `load_viewable_post` — 미존재/차단/visibility 검증
            2. 중복 검사 (composite PK 로 빠른 lookup)
            3. INSERT + count
            4. payload 합성 (본인이면 detail fetch skip — outer 가 어차피 fan-out 안 함)

        race 처리는 모듈 docstring 참조.
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

        # 본인→본인 — outer 가 fan-out skip 하므로 detail fetch 생략.
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
            post_preview=post.thumbnail_small_url,
        )


    # ──────────────────── 취소 ────────────────────

    @transactional
    async def remove_like(self, user_id: str, post_id: str) -> int:
        """좋아요 취소 — 게시물 가시성 검증 후 DELETE, 새 like_count 반환.

        가시성 검증을 add 와 동일하게 수행 — 중간에 owner 가 visibility 를 PRIVATE 로 바꾸면
        viewer 의 좋아요 취소 액션도 거절된다 (UX 자연스러움 vs 정합성 트레이드오프, 후자 채택).
        """
        post = await load_viewable_post(self._session, viewer_id=user_id, post_id=post_id)
        like_repo = FeedPostLikeRepository(self._session)

        existing = await like_repo.find_by_user_and_post(user_id, post.post_id)
        if existing is None:
            raise ValueError("좋아요를 누르지 않은 게시물입니다.")

        await like_repo.delete_by_user_and_post(user_id, post.post_id)
        like_count = await like_repo.count_by_post(post.post_id)
        logger.info("피드 좋아요 취소 (user_id={}, post_id={})", user_id, post.post_id)
        return like_count


    # ──────────────────── 조회 ────────────────────

    @transactional
    async def get_liked_users(
        self, viewer_id: str, post_id: str,
    ) -> list[LikedUserData]:
        """좋아요 누른 유저 목록 — 가시성 검증 후 프로필 포함 단일 JOIN 쿼리로 일괄 반환.

        viewer 가 게시물을 볼 수 없으면 좋아요 목록도 못 본다 (transitive 가시성).
        repository (`find_with_user_by_post`) 가 `feed_post_like ⨝ users ⨝ user_detail_inform`
        을 단일 SELECT 로 로드 — N+1 / batch 라운드트립 회피.

        detail 결손 (회원가입 미완료 등 비정상) 케이스는 `_to_liked_user_dto` 가 빈 문자열 /
        None 으로 fallback (chat 도메인 컨벤션 일치).
        """
        post = await load_viewable_post(self._session, viewer_id=viewer_id, post_id=post_id)
        like_repo = FeedPostLikeRepository(self._session)
        likes = await like_repo.find_with_user_by_post(post.post_id)
        return [self._to_liked_user_dto(like) for like in likes]


    # ──────────────────── 내부 유틸 ────────────────────

    @staticmethod
    def _to_liked_user_dto(like: FeedPostLike) -> LikedUserData:
        """FeedPostLike (with joinedload user.detail) → LikedUserData.

        FK CASCADE 로 user 결손은 발생 안 하지만 (like 가 함께 삭제됨), detail 결손은
        회원가입 미완료 등 비정상 상태에서 가능 — 빈 문자열 / None fallback 으로 응답
        형태 일관성 유지 (chat `_user_to_member_dto` 동일 패턴).
        """
        user = like.user
        detail = user.detail if user is not None else None
        return LikedUserData(
            user_id=like.user_id,
            user_name=detail.user_name if detail is not None else "",
            profile_image_url=detail.profile_image_url if detail is not None else None,
        )
