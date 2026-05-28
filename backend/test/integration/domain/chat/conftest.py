"""채팅 도메인 통합 테스트 공통 fixture (chat 서브디렉토리 전용).

실 Postgres (상위 conftest) + 실 Redis (hot/dedupe) + 실 Mongo 를 엮어 MessageService /
SessionService / RoomService 를 조립한다. Redis / Mongo 연결은 다음 환경변수로 제공:

    REDIS_TEST_URL    예) redis://localhost:6479
    MONGODB_TEST_URL  예) mongodb://cho:hyeonsang@localhost:27117/chohyeonsang_test?authSource=admin

환경변수 누락 시 pytest.skip — POSTGRES_TEST_URL 과 동일 패턴.

이 conftest 의 patch fixture 는 **opt-in** (autouse 아님). ``message_service`` /
``session_service`` / ``direct_room`` 을 주입하는 테스트에만 Redis/Mongo 가 요구된다.
기존 ``test_room_flow.py`` / ``test_db_constraints.py`` 는 Redis 를 자체 stub 하므로
영향이 없다.
"""
from unittest.mock import AsyncMock, MagicMock
import redis.asyncio as aioredis
import pytest_asyncio
import pytest
import os
from motor.motor_asyncio import AsyncIOMotorClient

from app.domain.chat.service.session import SessionService
from app.domain.chat.service.message import MessageService
from app.domain.chat.model.chat_message import create_indexes as create_chat_message_indexes
from app.core.chat.lua_script import lua_scripts


def _require_env(name: str) -> str:
    url = os.getenv(name)
    if not url:
        pytest.skip(
            f"{name} 환경변수가 설정되지 않아 chat 통합 테스트를 건너뜁니다. "
            "smoke compose 를 먼저 띄운 뒤 아래 예시로 실행:\n"
            "  docker compose -f scripts/chat/docker-compose.smoke.yml up -d --wait\n"
            "  POSTGRES_TEST_URL='postgresql+asyncpg://cho:hyeonsang@localhost:5532/chohyeonsang_test' \\\n"
            "  REDIS_TEST_URL='redis://localhost:6479' \\\n"
            "  MONGODB_TEST_URL='mongodb://cho:hyeonsang@localhost:27117/chohyeonsang_test?authSource=admin' \\\n"
            "  uv run pytest test/integration/domain/chat",
            allow_module_level=False,
        )
    return url


# ──────────────────────────────────────────────────────────────────
# 실 연결 fixture (function scope — 매 테스트 fresh)
# ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def redis_hot():
    """hot Redis (DB 0). Lua 스크립트 로드 후 반환. 매 테스트 전/후 FLUSHDB."""
    base = _require_env("REDIS_TEST_URL")
    client = aioredis.from_url(f"{base}/0", decode_responses=True, encoding="utf-8")
    await client.flushdb()
    # lua_scripts 는 모듈 싱글톤. 테스트마다 새 client 로 rebind.
    lua_scripts.load(client)
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest_asyncio.fixture
async def redis_dedupe():
    """dedupe Redis (DB 1)."""
    base = _require_env("REDIS_TEST_URL")
    client = aioredis.from_url(f"{base}/1", decode_responses=True, encoding="utf-8")
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest_asyncio.fixture
async def mongo_db():
    """MONGODB_TEST_URL 로 지정된 DB. `chat_message` 컬렉션 초기화 + 인덱스 생성."""
    url = _require_env("MONGODB_TEST_URL")
    client = AsyncIOMotorClient(url, tz_aware=True)
    db = client.get_default_database()
    await db.chat_message.drop()
    await create_chat_message_indexes(db)
    try:
        yield db
    finally:
        await db.chat_message.drop()
        client.close()


# ──────────────────────────────────────────────────────────────────
# 서비스 조립 (opt-in — 이 fixture 를 주입하는 테스트만 실 연결 요구)
# ──────────────────────────────────────────────────────────────────

@pytest.fixture
def patch_external_clients(monkeypatch, redis_hot, redis_dedupe, mongo_db):
    """MessageService / SessionService / RoomService 가 참조하는 전역 의존성을 실 연결로 교체.

    각 서비스 모듈에서 ``from app.core.redis import get_redis_client`` 으로 import 된
    심볼을 **바인딩된 모듈 경로** 에서 직접 setattr 해야 한다. 원본 ``app.core.redis``
    만 건드리면 이미 import 된 서비스 모듈은 옛 참조를 계속 쓴다.
    """
    async def _hot():
        return redis_hot

    async def _dedupe():
        return redis_dedupe

    monkeypatch.setattr(
        "app.domain.chat.service.message.get_redis_client", _hot,
    )
    monkeypatch.setattr(
        "app.domain.chat.service.message.get_redis_dedupe_client", _dedupe,
    )
    monkeypatch.setattr(
        "app.domain.chat.service.session.get_redis_client", _hot,
    )
    monkeypatch.setattr(
        "app.domain.chat.service.room.get_redis_client", _hot,
    )
    monkeypatch.setattr(
        "app.domain.chat.service.message_history.get_redis_client", _hot,
    )
    monkeypatch.setattr(
        "app.domain.chat.service.block_cache.get_redis_client", _hot,
    )
    # mongodb 싱글톤의 database 속성 교체 (최초엔 None 이므로 raising=False)
    monkeypatch.setattr(
        "app.database.session.mongodb.database", mongo_db, raising=False,
    )


@pytest.fixture
def chat_fanout_stub() -> MagicMock:
    """fan-out 호출 검증용 mock. test_room_flow.py 의 fanout_stub 과 이름을 분리.

    `FanoutService` 의 비동기 메서드 전체를 AsyncMock 으로 셋업 — sync MagicMock 으로
    남아있으면 `await stub.method(...)` 시 `TypeError: object MagicMock can't be used
    in 'await' expression`. subscribe/unsubscribe 는 room 변경 (`create_group_room` /
    `invite_users` / `leave_room` / `kick_user` / 재가입) 경로 전부에서 await 된다.
    """
    mock = MagicMock(name="chat-fanout")
    mock.fan_out_to_user = AsyncMock()
    mock.fan_out_to_session = AsyncMock()
    mock.fan_out_to_room = AsyncMock()
    mock.subscribe_user_to_room = AsyncMock()
    mock.unsubscribe_user_from_room = AsyncMock()
    return mock


@pytest.fixture
def chat_fcm_stub() -> MagicMock:
    """FCM 발송은 fire-and-forget — 본 비즈 테스트는 push 호출 여부와 무관."""
    mock = MagicMock(name="chat-fcm")
    mock.send_chat_push = AsyncMock(return_value=0)
    mock.register_token = AsyncMock()
    mock.unregister_token = AsyncMock()
    return mock


@pytest.fixture
def message_service(uow, chat_fanout_stub, chat_fcm_stub, patch_external_clients) -> MessageService:
    """공유 서비스 인스턴스. 동시 호출 테스트에서는 task 별 신규 인스턴스를 만들어야
    한다 (``@transactional`` 이 ``self._session`` 을 변경하므로 인스턴스 공유 시 race)."""
    return MessageService(uow=uow, fanout_service=chat_fanout_stub, fcm_service=chat_fcm_stub)


@pytest.fixture
def session_service(chat_fanout_stub, patch_external_clients) -> SessionService:
    return SessionService(fanout_service=chat_fanout_stub)


@pytest_asyncio.fixture
async def direct_room(
    uow, seed_users, chat_fanout_stub, message_service, patch_external_clients,
):
    """(room_id, user_a, user_b) 반환. RoomService 를 거쳐 방 + 멤버 + Redis 캐시까지 세팅.

    Phase 2 에서 RoomService 가 MessageService (시스템 메시지용) 에 의존하게 됐으므로
    `message_service` fixture 도 주입. 1:1 방 생성은 시스템 메시지를 발행하지 않으므로
    실제로 호출되진 않지만 생성자 인자는 채워야 한다.
    """
    # 순환 import 회피를 위해 fixture 내부 import
    from app.domain.chat.service.room import RoomService

    user_a, user_b = await seed_users(2)
    room_svc = RoomService(
        uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
    )
    result = await room_svc.create_direct_room(me_id=user_a, peer_user_id=user_b)
    chat_fanout_stub.reset_mock()  # 방 생성으로 찍힌 호출 제거
    return result.chat_room_id, user_a, user_b
