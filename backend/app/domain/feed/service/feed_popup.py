"""피드 팝업 서비스 — 다른 유저 프로필 미리보기 합성.

`GET /feed/popup/{user_id}` 의 비즈니스 로직.

흐름:
    1. UserRepository 로 owner 의 user + detail + travel_styles 일괄 조회 (단일 SELECT)
    2. user 미존재 / detail 결손 → PopupTargetNotFoundError (404)
    3. resolve_viewer_visibilities 로 차단/친구 합성 → 차단이면 FeedBlockedError (403)
    4. find_by_owner(limit=POPUP_FEED_LIMIT) 로 최근 9개 피드 + 카운트 일괄 조회
    5. DTO 합성

크로스 도메인:
    - auth UserRepository / TravelStyle 직접 import — chat 도메인의 cross-repo 패턴과 동일.
    - service-to-service 의존 회피 (`profile_service.get_xxx` 안 부름).

권한 / 정보 누출:
    - user 미존재 와 회원가입 미완료 (detail=None) 두 케이스를 같은 404 로 일원화 — 회원가입
      상태 enumeration 차단.
    - 차단 관계는 user 정보를 노출하지 않고 진입 자체 거절 (403).
    - viewer == owner 도 정상 동작 (모든 visibility 노출, fast-path).
"""
from app.domain.feed.service.exception import PopupTargetNotFoundError
from app.domain.feed.service.access import resolve_viewer_visibilities
from app.domain.feed.repository.feed_post import FeedPostRepository
from app.domain.feed.dto.feed_popup import POPUP_FEED_LIMIT, FeedPopupData
from app.domain.feed.dto.feed_post import FeedPostData
from app.domain.auth.repository.user import UserRepository
from app.database.session import UnitOfWork, transactional
from app.core.logger import get_logger


logger = get_logger("feed.popup.service")


class FeedPopupService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow


    @transactional
    async def get_popup(self, viewer_id: str, owner_id: str) -> FeedPopupData:
        """팝업 응답 합성 — 프로필 5종 + 최근 9개 피드.

        실패 매핑:
            - user 미존재 / 회원가입 미완료 → PopupTargetNotFoundError (404)
            - 차단 관계               → FeedBlockedError (403, access 가 raise)
        """
        # 1. user + detail + travel_styles 단일 SELECT (joinedload).
        user_repo = UserRepository(self._session)
        owner = await user_repo.find_by_id_with_profile(owner_id)
        if owner is None or owner.detail is None:
            # 두 케이스 (없음 / 회원가입 미완료) 동일 404 — enumeration 회피.
            raise PopupTargetNotFoundError("존재하지 않는 유저입니다.")

        # 2. 가시성 / 차단 — viewer == owner fast-path 포함. 차단 시 FeedBlockedError raise.
        visibilities = await resolve_viewer_visibilities(
            self._session, viewer_id=viewer_id, owner_id=owner_id,
        )

        # 3. 최근 9개 피드 + 카운트 + viewer 좋아요 여부 일괄 조회 (cursor 없음, popup 은 첫 페이지만).
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

        매핑 로직 중복은 작은 비용 vs service-to-service 의존 (FeedPostService 주입) 회피 이득.
        FeedPostData 의 필드 변경 시 두 곳 갱신 필요 — 회귀 가드는 schema 테스트가 잡음.
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
