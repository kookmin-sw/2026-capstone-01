"""피드 팝업 — 다른 유저 프로필 미리보기 합성 (`GET /feed/popup/{user_id}`).

흐름: user+detail+travel_styles 조회 → 차단/친구 합성 → 최근 9개 피드 → DTO.

user 미존재 / detail 결손은 같은 404 로 일원화 (회원가입 상태 enumeration 차단).
"""
from app.domain.feed.service.exception import PopupTargetNotFoundError
from app.domain.feed.service.access import resolve_viewer_visibilities
from app.domain.feed.repository.feed_post import FeedPostRepository
from app.domain.feed.dto.feed_post import FeedPostData
from app.domain.feed.dto.feed_popup import POPUP_FEED_LIMIT, FeedPopupData
from app.domain.auth.repository.user import UserRepository
from app.database.session import UnitOfWork, transactional
from app.core.logger import get_logger


logger = get_logger("feed.popup.service")


class FeedPopupService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow


    @transactional
    async def get_popup(self, viewer_id: str, owner_id: str) -> FeedPopupData:
        """프로필 5종 + 최근 9개 피드 합성.

        404: user 미존재 / 회원가입 미완료.
        403: 차단 관계 (access 가 raise).
        """
        user_repo = UserRepository(self._session)
        owner = await user_repo.find_by_id_with_profile(owner_id)
        if owner is None or owner.detail is None:
            raise PopupTargetNotFoundError("존재하지 않는 유저입니다.")

        # viewer == owner fast-path 포함. 차단 시 FeedBlockedError.
        visibilities = await resolve_viewer_visibilities(
            self._session, viewer_id=viewer_id, owner_id=owner_id,
        )

        # popup 은 첫 페이지만 (cursor 없음).
        feed_repo = FeedPostRepository(self._session)
        rows = await feed_repo.find_by_owner(
            owner_id=owner_id,
            visibilities=visibilities,
            cursor=None,
            limit=POPUP_FEED_LIMIT,
            viewer_id=viewer_id,
        )

        return FeedPopupData(
            user_id=owner.user_id,
            user_name=owner.detail.user_name,
            nationality=owner.detail.nationality,
            travel_styles=[s.style for s in owner.travel_styles],
            profile_image_url=owner.detail.profile_image_url,
            feed_items=[self._to_feed_dto(r) for r in rows],
        )


    @staticmethod
    def _to_feed_dto(row) -> FeedPostData:
        """`FeedPostWithCounts` → `FeedPostData`. `FeedPostService._to_dto` 와 동일 매핑.

        중복은 service-to-service 의존 회피 비용 — schema 테스트가 회귀 가드.
        """
        post = row.post
        return FeedPostData(
            post_id=post.post_id,
            user_id=post.user_id,
            visibility=post.visibility,
            caption=post.caption,
            original_url=post.original_url,
            thumbnail_small_url=post.thumbnail_small_url,
            thumbnail_medium_url=post.thumbnail_medium_url,
            like_count=row.like_count,
            comment_count=row.comment_count,
            is_liked=row.is_liked,
            created_at=post.created_at,
            updated_at=post.updated_at,
        )
