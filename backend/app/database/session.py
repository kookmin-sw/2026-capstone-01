from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import async_sessionmaker
from functools import wraps
from contextvars import ContextVar

from app.core.instrumentation import db_transaction_inc
from app.core.context import db_route_var


# ──────────────────── RDB ────────────────────

# 트랜잭션 전파용 — `@transactional` 이 nested 호출 시 같은 session 재사용 여부 판정.
_current_session: ContextVar = ContextVar('_current_session', default=None)


class UnitOfWork:
    def __init__(self, session: async_sessionmaker):
        self.session_factory = session


    async def __aenter__(self):
        self.session = self.session_factory()
        return self.session


    async def __aexit__(self, exc_type, exc, tb):
        # commit 자체가 실패할 수 있어 try/except 로 'other' 라벨을 분리.
        route = db_route_var.get()
        try:
            if exc:
                await self.session.rollback()
                db_transaction_inc(route, "rollback")
            else:
                try:
                    await self.session.commit()
                    db_transaction_inc(route, "commit")
                except Exception:
                    db_transaction_inc(route, "other")
                    raise
        finally:
            await self.session.close()


def transactional(fn):
    """nested 호출은 기존 트랜잭션에 참여, 최상위 호출만 새 UoW 를 연다."""
    @wraps(fn)
    async def wrapper(self, *args, **kwargs):
        existing = _current_session.get()
        if existing is not None:
            self._session = existing
            return await fn(self, *args, **kwargs)

        async with self.uow as session:
            token = _current_session.set(session)
            self._session = session
            try:
                return await fn(self, *args, **kwargs)
            finally:
                _current_session.reset(token)
                self._session = None
    return wrapper

Base = declarative_base()


# ──────────────────── NoSQL ────────────────────

from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from beanie import init_beanie

from app.domain.tripmate.model.tripmate_post_draft import TripmatePostDraft
from app.domain.tripmate.model.tripmate_search_history import TripmateSearchHistory
from app.domain.tripmate.model.tripmate_image import TripmateImage
from app.domain.tour.model.place import Place
from app.domain.tour.model.tour_search_history import TourSearchHistory
from app.domain.friend.model.search_history import FriendSearchHistory
from app.domain.chat.model.chat_message import create_indexes as create_chat_message_indexes
from app.domain.auth.model.withdrawal_request import WithdrawalRequest
from app.domain.notification.model.inbox import InboxItem
from app.config.setting import settings


# Mongo socket-level timeout — Mongo hang 시 코루틴 영구 stuck 차단.
#
# Motor 기본값 (socketTimeoutMS=None) 은 무한 대기 → primary step-down / disk sync /
# 네트워크 partition 시 await 영원히 정지. measure_mongo_op 의 try/finally 도 도달 못 해
# 메트릭 침묵 (장애인데 안 보이는 무관측 상태) → 명시 cap 필수.
#
# socketTimeoutMS 10s — aggregate / 복잡한 find 까지 여유. 그보다 긴 query 는 호출처에서
# maxTimeMS 로 별도 제어.
# serverSelectionTimeoutMS 5s — 기본 30s 는 failover 중 사용자 30초 hang. 정상 failover 는
# ms 단위라 5s 면 빠른 fail + retry.
# health.py 의 _mongo_ping (asyncio.wait_for 2s) 가 항상 먼저 발화 — 두 timeout 이 layer 별로 동작.
_MONGO_SERVER_SELECTION_TIMEOUT_MS = 5000
_MONGO_CONNECT_TIMEOUT_MS = 5000
_MONGO_SOCKET_TIMEOUT_MS = 10000


class MongoDB:
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None # type: ignore
        self.database: Optional[AsyncIOMotorDatabase] = None # type: ignore


    async def connect(self):
        self.client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            maxPoolSize=100,
            minPoolSize=10,
            tz_aware=True,
            serverSelectionTimeoutMS=_MONGO_SERVER_SELECTION_TIMEOUT_MS,
            connectTimeoutMS=_MONGO_CONNECT_TIMEOUT_MS,
            socketTimeoutMS=_MONGO_SOCKET_TIMEOUT_MS,
        )
        self.database = self.client[settings.MONGODB_NAME]

        await init_beanie(
            database=self.database,
            document_models=[
                WithdrawalRequest,
                TripmatePostDraft,
                TripmateSearchHistory,
                TripmateImage,
                Place,
                TourSearchHistory,
                FriendSearchHistory,
                InboxItem,
            ]
        )

        # 채팅 메시지는 motor 네이티브 — beanie document 대신 인덱스만 초기화.
        await create_chat_message_indexes(self.database)


    async def disconnect(self):
        if self.client:
            self.client.close()

mongodb = MongoDB()


async def init_mongodb():
    await mongodb.connect()


async def close_mongodb():
    await mongodb.disconnect()
