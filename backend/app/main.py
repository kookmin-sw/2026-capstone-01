import os
import random
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.middleware.tracking import (
    RequestIDMiddleware,
    ErrorTrackingMiddleware,
    SecurityHeadersMiddleware,
)
from app.middleware.auth import BearerTokenMiddleware, LoginCookieMiddleware, RegisterCheckMiddleware
from app.domain.chat.worker.reconcile import (
    start_reconcile_scheduler,
    stop_reconcile_scheduler,
)
from app.domain.chat.worker.node_registry import (
    start_node_registry,
    stop_node_registry,
)
from app.domain.chat.worker.fanout_dispatcher import (
    start_fanout_dispatcher,
    stop_fanout_dispatcher,
)
from app.domain.auth.worker.withdraw_purge import (
    start_withdraw_purge_scheduler,
    stop_withdraw_purge_scheduler,
)
from app.database.session import init_mongodb, close_mongodb
import app.database.model # Relation Lazy Load 문제 해결하기 위한 import!
from app.core.ai.tour_planner.load import TourPlanner
from app.core.logger import setup_logging, get_logger
from app.core.ai.menu_ocr.load import MenuOcr
from app.core.redis import get_redis_client, get_redis_dedupe_client, close_redis
from app.core.fcm import init_fcm, close_fcm
from app.core.chat.lua_script import lua_scripts
from app.container import Container
from app.config.setting import settings
from app.api.v1.router import api_router


logger = get_logger("main")


def create_app() -> FastAPI:
    """FastAPI 애플리케이션 팩토리"""
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # startup
        setup_logging()

        # force_jump Lua 호출 시 사용할 jitter 엔트로피 보강
        random.seed(int.from_bytes(os.urandom(16), "big"))

        await init_mongodb()

        # Redis 양쪽 DB 커넥션 pre-warm 후 hot 클라이언트에 Lua 스크립트 등록.
        hot_redis = await get_redis_client()
        await get_redis_dedupe_client()
        lua_scripts.load(hot_redis)

        # FCM Admin SDK 초기화 — 워커가 푸시를 보낼 수 있어야 하므로 워커 시작 전에 호출.
        init_fcm()

        # 채팅 reconcile 워커 — last_message_* 정합성 복구 + unread 복구 entry point 주입
        # (ws.py 의 recover_unread 경로도 같은 session_factory 공유)
        start_reconcile_scheduler(app.container.session_factory())

        # 채팅 멀티 노드 fan-out 인프라 — FANOUT_MODE=in_process 면 둘 다 no-op.
        # 순서 중요 (race window 차단):
        #   1) dispatcher 가 먼저 `node:{NODE_ID}` 채널 SUBSCRIBE 까지 await
        #   2) 그 다음 node_registry 가 ZSET 에 자기 노드 등록 → 다른 노드의 publisher 가
        #      list_active_nodes 로 우리를 인지한 시점엔 이미 채널 활성. 반대 순서면 ZSET
        #      등록 ~ SUBSCRIBE 사이 publish 가 누락됨.
        await start_fanout_dispatcher(app.container.fanout_service())
        await start_node_registry()

        # 탈퇴 영구 삭제 워커 — 매일 KST 04:00 발화. RDB / Mongo / S3 / Redis 모두 사용하므로
        # init_mongodb / Redis pre-warm 이후에 시작.
        start_withdraw_purge_scheduler(app.container.session_factory())

        MenuOcr().load()
        await TourPlanner().load()
        logger.info("Starting application in {} mode", settings.ENVIRONMENT)

        yield

        # shutdown — 워커들이 Mongo/Redis 를 쓰므로 이 둘을 닫기 전에 먼저 멈춘다.
        # 순서 중요 (startup 의 거울): node_registry 를 먼저 정리해 다른 노드의 publisher
        # 가 다음 list_active_nodes 호출부터 우리를 즉시 제외하게 한 뒤, 디스패처가 안전히
        # unsubscribe. 반대 순서면 디스패처 정지 ~ ZSET deregister 사이 publish 가 drop.
        await stop_withdraw_purge_scheduler()
        await stop_reconcile_scheduler()
        await stop_node_registry()
        await stop_fanout_dispatcher()
        close_fcm()
        await close_mongodb()
        await close_redis()
        logger.info("Application shutting down")

    # DI Container 초기화 및 wiring
    container = Container()
    container.wire(modules=[
        "app.domain.auth.router.login",
        "app.domain.auth.router.register",
        "app.domain.auth.router.profile",
        "app.domain.auth.router.withdraw",
        "app.domain.tripmate.router.tripmate_post",
        "app.domain.tripmate.router.tripmate_search_history",
        "app.domain.tripmate.router.tripmate_image",
        "app.domain.menu_ai.router.menu_ocr",
        "app.domain.tour.router.place",
        "app.domain.tour.router.recommend",
        "app.domain.tour.router.tour_search_history",
        "app.domain.tour.router.tour_plan",
        "app.domain.friend.router.friendship",
        "app.domain.friend.router.user_block",
        "app.domain.friend.router.detail",
        "app.domain.friend.router.search",
        "app.domain.friend.router.search_history",
        "app.domain.chat.router.room",
        "app.domain.chat.router.message",
        "app.domain.chat.router.ws",
        "app.domain.public.router.share",
        "app.domain.notification.router.fcm_token",
        "app.domain.notification.router.mute",
        "app.domain.notification.router.inbox",
        "app.domain.feed.router.feed_post",
        "app.domain.feed.router.feed_user",
        "app.domain.feed.router.feed_post_like",
        "app.domain.feed.router.feed_post_comment",
        "app.domain.feed.router.feed_popup",
    ])


    app = FastAPI(
        title="Krip API",
        description="Krip 서버",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # 미들웨어 (등록 역순으로 실행됨 → CORS가 가장 먼저 실행)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RegisterCheckMiddleware)
    app.add_middleware(LoginCookieMiddleware)
    app.add_middleware(BearerTokenMiddleware)
    app.add_middleware(ErrorTrackingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # CORS (가장 마지막에 등록 → 가장 바깥쪽에서 실행되어 모든 응답에 CORS 헤더 추가)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            settings.FRONTEND_URL,
            settings.LOCAL_FRONTEND_URL,
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 라우터
    app.include_router(api_router)
    
    app.container = container
    
    return app
    
    
app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        reload=not settings.is_production,
        log_config=None,
    )