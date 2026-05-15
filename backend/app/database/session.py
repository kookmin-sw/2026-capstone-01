from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import async_sessionmaker
from functools import wraps
from contextvars import ContextVar

from app.core.context import db_route_var
from app.core.instrumentation import db_transaction_inc

"""
RDB
"""

_current_session: ContextVar = ContextVar('_current_session', default=None) # 트랜잭션 전파 관리

class UnitOfWork:
    def __init__(self, session: async_sessionmaker):
        self.session_factory = session

    async def __aenter__(self):
        self.session = self.session_factory()
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        # 트랜잭션 결과 카운트 — route 라벨은 contextvar 에서 회수.
        # commit 자체가 실패할 수 있어 try/except 로 'other' 를 분리한다.
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
    @wraps(fn)
    async def wrapper(self, *args, **kwargs):
        existing = _current_session.get()
        if existing is not None:
            # 이미 트랜잭션이 열려 있으면 기존 세션에 참여
            self._session = existing
            return await fn(self, *args, **kwargs)

        # 새 트랜잭션 시작
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

"""
NoSQL
"""

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


# Mongo socket-level timeout 정책 — Mongo hang 시 코루틴이 영구 stuck 되는 것을 차단.
#
# Motor 기본값 (socketTimeoutMS=None) 은 무한 대기라, replica set primary step-down /
# mongod disk sync / 네트워크 partition 시 호출 코루틴이 영원히 await 상태로 머문다.
# measure_mongo_op 의 try/finally 조차 도달 못 해 MONGO_OP_DURATION / MONGO_OP_ERRORS_TOTAL
# 모두 침묵 — 장애 났는데 메트릭에 안 보이는 무관측 상태.
#
# Redis 측 (core/redis.py:_REDIS_SOCKET_TIMEOUT_SEC=5.0) 과 평행하지만 Mongo 는 query
# 가 더 길 수 있어 (aggregate, 복잡한 find) socketTimeoutMS 만 10s 로 더 보수적.
# 그보다 긴 query 가 필요한 케이스는 호출처에서 query-level maxTimeMS 옵션으로 별도 제어.
#
# serverSelectionTimeoutMS 30s 기본은 failover 중 사용자 트래픽 30초 hang 을 의미해
# 너무 길다. 5s 면 빠른 fail 후 retry / alert 흐름이 정상 작동. 정상 failover 는 ms
# 단위라 5s 안에 충분히 끝남.
#
# health.py 의 _mongo_ping 은 asyncio.wait_for(2s) 로 더 짧게 감싸 항상 health 측이
# 먼저 발화 — 두 timeout 이 충돌 없이 layer 별로 동작한다.
_MONGO_SERVER_SELECTION_TIMEOUT_MS = 5000
_MONGO_CONNECT_TIMEOUT_MS = 5000
_MONGO_SOCKET_TIMEOUT_MS = 10000


class MongoDB:
    """MongoDB 클라이언트 및 데이터베이스 관리"""
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None # type: ignore
        self.database: Optional[AsyncIOMotorDatabase] = None # type: ignore

    async def connect(self):
        """MongoDB 연결 및 초기화"""
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

        # 채팅 메시지는 motor 네이티브로 다루므로 beanie document 대신 인덱스만 초기화
        await create_chat_message_indexes(self.database)
        
    async def disconnect(self):
        """MongoDB 연결 종료"""
        if self.client:
            self.client.close()
            
mongodb = MongoDB()


async def init_mongodb():
    """MongoDB 초기화 (앱 시작 시 호출)"""
    await mongodb.connect()
    

async def close_mongodb():
    """MongoDB 종료 (앱 종료 시 호출)"""
    await mongodb.disconnect()