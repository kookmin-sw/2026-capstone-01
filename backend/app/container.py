from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from dependency_injector import containers, providers

from app.domain.tripmate.service.tripmate_search_history import TripmateSearchHistoryService
from app.domain.tripmate.service.tripmate_post_like import TripmatePostLikeService
from app.domain.tripmate.service.tripmate_post_draft import TripmatePostDraftService
from app.domain.tripmate.service.tripmate_post import TripmatePostService
from app.domain.tripmate.service.tripmate_image import TripmateImageService
from app.domain.translation.service.translation import TranslationService
from app.domain.tour.service.tour_search_history import TourSearchHistoryService
from app.domain.tour.service.tour_plan import TourPlanService
from app.domain.tour.service.recommend import RecommendService
from app.domain.tour.service.place import PlaceService
from app.domain.tour.service.favorite_place import FavoritePlaceService
from app.domain.public.service.share_plan import SharePlanService
from app.domain.notification.service.mute import MuteService
from app.domain.notification.service.inbox import InboxService
from app.domain.notification.service.fcm import FcmService
from app.domain.menu_ai.service.menu_ocr import MenuOcrService
from app.domain.friend.service.user_block import UserBlockService
from app.domain.friend.service.search_history import FriendSearchHistoryService
from app.domain.friend.service.search import FriendSearchService
from app.domain.friend.service.friendship import FriendshipService
from app.domain.friend.service.friend_detail import FriendDetailService
from app.domain.feed.service.feed_post_like import FeedPostLikeService
from app.domain.feed.service.feed_post_comment import FeedPostCommentService
from app.domain.feed.service.feed_post import FeedPostService
from app.domain.feed.service.feed_popup import FeedPopupService
from app.domain.chat.service.user_purge_cache import UserPurgeCacheService
from app.domain.chat.service.session import SessionService
from app.domain.chat.service.room import RoomService
from app.domain.chat.service.message_history import MessageHistoryService
from app.domain.chat.service.message import MessageService
from app.domain.chat.service.fanout import FanoutService
from app.domain.chat.service.block_cache import BlockCacheService
from app.domain.auth.service.withdraw import WithdrawService
from app.domain.auth.service.signup import SignupService
from app.domain.auth.service.register import RegisterService
from app.domain.auth.service.profile import ProfileService
from app.database.session import UnitOfWork
from app.config.setting import settings


class Container(containers.DeclarativeContainer):
    """DI Container — 의존성 선언"""

    engine = providers.Singleton(
        create_async_engine,
        settings.POSTGRES_URL,
        echo=False,
        future=True,
    )

    session_factory = providers.Singleton(
        async_sessionmaker,
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    uow = providers.Factory(UnitOfWork, session=session_factory)

    # 인박스 (Mongo, stateless) — fan-out / cascade 진입점. RDB 의존성이 없어 가장 먼저
    # 선언 → 모든 도메인 service 가 자기 자리에서 자유롭게 의존할 수 있도록.
    inbox_service = providers.Factory(InboxService)

    # 서비스 계층 주입
    signup_service = providers.Factory(SignupService, uow=uow)
    register_service = providers.Factory(RegisterService, uow=uow)
    profile_service = providers.Factory(ProfileService, uow=uow)
    # withdraw_service 는 chat 의 user_purge_cache_service 에 의존하므로
    # chat 인프라 선언 뒤로 이동 (아래 user_block_service 패턴과 동일).
    tripmate_post_draft_service = providers.Factory(TripmatePostDraftService)
    tripmate_post_service = providers.Factory(
        TripmatePostService,
        uow=uow,
        draft_service=tripmate_post_draft_service,
        inbox_service=inbox_service,
    )
    tripmate_post_like_service = providers.Factory(
        TripmatePostLikeService, uow=uow, inbox_service=inbox_service,
    )
    tripmate_search_history_service = providers.Factory(TripmateSearchHistoryService)
    tripmate_image_service = providers.Factory(TripmateImageService, uow=uow)

    # 메뉴 AI
    menu_ocr_service = providers.Factory(MenuOcrService)

    # 번역 (자유 문장 ko ↔ en — 현재 구현체: Papago)
    translation_service = providers.Factory(TranslationService)

    # 관광
    place_service = providers.Factory(PlaceService, uow=uow)
    favorite_place_service = providers.Factory(FavoritePlaceService, uow=uow)
    tour_search_history_service = providers.Factory(TourSearchHistoryService)
    recommend_service = providers.Factory(RecommendService)
    tour_plan_service = providers.Factory(TourPlanService, uow=uow)

    # 공개 (인증 없이 접근 가능)
    share_plan_service = providers.Factory(SharePlanService, uow=uow)

    # 채팅 — 인프라 (Singleton: 프로세스 내 전역 상태 유지)
    fanout_service = providers.Singleton(FanoutService)
    session_service = providers.Singleton(SessionService, fanout_service=fanout_service)

    # 회원 탈퇴 cleanup 훅 — auth 도메인의 WithdrawService 가 의존. block_cache_service 와
    # 동일 패턴 (cross-domain anti-corruption layer).
    user_purge_cache_service = providers.Factory(
        UserPurgeCacheService, session_service=session_service,
    )

    # auth — 회원 탈퇴 시 chat 세션 / 데이터 cleanup 훅 의존. friend ← chat 처럼 의존
    # 그래프상 chat 인프라 뒤에 배치.
    withdraw_service = providers.Factory(
        WithdrawService,
        uow=uow,
        inbox_service=inbox_service,
        user_purge_cache_service=user_purge_cache_service,
    )

    # 알림 (FCM) — message_service 가 의존하므로 그보다 먼저 선언.
    fcm_service = providers.Factory(FcmService, uow=uow)
    mute_service = providers.Factory(MuteService, uow=uow)

    # 채팅 — 비즈 (Factory: 호출마다 UoW 새로 바인딩)
    #   - message_service / block_cache_service 는 room_service / user_block_service 보다
    #     먼저 선언 (system 메시지 발행 / 차단 캐시 무효화 훅 의존성)
    message_service = providers.Factory(
        MessageService, uow=uow, fanout_service=fanout_service, fcm_service=fcm_service,
    )
    room_service = providers.Factory(
        RoomService, uow=uow, fanout_service=fanout_service, message_service=message_service,
    )
    message_history_service = providers.Factory(MessageHistoryService, uow=uow)
    block_cache_service = providers.Factory(BlockCacheService, uow=uow)

    # 친구 — chat 의 block_cache_service 에 의존
    friendship_service = providers.Factory(FriendshipService, uow=uow)
    user_block_service = providers.Factory(
        UserBlockService, uow=uow, block_cache_service=block_cache_service,
    )
    friend_detail_service = providers.Factory(FriendDetailService, uow=uow)
    friend_search_service = providers.Factory(FriendSearchService, uow=uow)
    friend_search_history_service = providers.Factory(FriendSearchHistoryService)

    # 피드 — 좋아요/댓글 fan-out + 게시글 삭제 cascade (soft hide) 모두 인박스 의존.
    # 댓글 단건 삭제는 cascade 안 함.
    feed_post_service = providers.Factory(
        FeedPostService, uow=uow, inbox_service=inbox_service,
    )
    feed_post_like_service = providers.Factory(
        FeedPostLikeService, uow=uow, inbox_service=inbox_service,
    )
    feed_post_comment_service = providers.Factory(
        FeedPostCommentService, uow=uow, inbox_service=inbox_service,
    )
    feed_popup_service = providers.Factory(FeedPopupService, uow=uow)
