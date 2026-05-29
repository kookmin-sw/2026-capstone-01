"""notification 도메인 통합 테스트 공통 fixture.

서비스 → 레포지토리 → 실 PostgreSQL/Mongo 까지 검증한다. FCM 외부 SDK 만 mock —
실제 네트워크 호출 없이 가드 체인과 토큰 정리 로직의 정확성을 본다.

fcm-token / mute 흐름은 RDB 만 터치 (실 Mongo 불필요). 인박스 (`inbox` 컬렉션)
흐름은 실 Mongo 가 필요하므로 `mongo_db` / `inbox_service` fixture 가 opt-in 으로
제공됨 — chat 도메인의 ``patch_external_clients`` 패턴과 일관.
"""
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import select
import pytest_asyncio
import pytest
import os
from motor.motor_asyncio import AsyncIOMotorClient

from app.domain.notification.service.mute import MuteService
from app.domain.notification.service.inbox import InboxService
from app.domain.notification.service.fcm import FcmService
from app.domain.notification.model.inbox import InboxItem
from app.domain.notification.model.fcm_token import FcmToken
from app.domain.chat.model.chat_room_member import ChatRoomMember
from app.domain.chat.model.chat_room import ChatRoom, ChatRoomType
from app.domain.auth.model.user import User


def _require_mongo_url() -> str:
    url = os.getenv("MONGODB_TEST_URL")
    if not url:
        pytest.skip(
            "MONGODB_TEST_URL 환경변수가 설정되지 않아 인박스 통합 테스트를 건너뜁니다.",
            allow_module_level=False,
        )
    return url


@pytest.fixture
def mute_service(uow) -> MuteService:
    return MuteService(uow=uow)


@pytest.fixture
def fcm_service(uow) -> FcmService:
    return FcmService(uow=uow)


@pytest_asyncio.fixture
async def seed_room_with_members(session_factory, seed_users):
    """그룹방 1개 + 활성 멤버 N명 시드. (room_id, [user_id...]) 반환.

    members 의 `notification_muted` 는 모두 NULL 로 시작 — 테스트에서 변경.
    """
    async def _seed(member_count: int = 2):
        user_ids = await seed_users(member_count)
        async with session_factory() as session:
            room = ChatRoom(
                type=ChatRoomType.GROUP,
                title="IT room",
                creator_id=user_ids[0],
            )
            session.add(room)
            await session.flush()  # chat_room_id 생성
            for uid in user_ids:
                session.add(ChatRoomMember(
                    chat_room_id=room.chat_room_id,
                    user_id=uid,
                ))
            await session.commit()
            return room.chat_room_id, user_ids

    return _seed


@pytest_asyncio.fixture
async def fcm_messaging_stub(monkeypatch):
    """`firebase_admin.messaging.send_each_for_multicast` 와 `get_fcm_app` 을 stub.

    테스트마다 `set_responses(success=[...], errors=[...])` 로 응답 시나리오 주입.
    """
    state = {"calls": [], "responses": [], "errors": []}

    def _set_responses(success: list[bool], errors: list | None = None):
        state["responses"] = success
        state["errors"] = errors or [None] * len(success)

    def _fake_send_each_for_multicast(message, app=None):
        # SDK 가 동기 함수 — service 가 asyncio.to_thread 로 감싸 호출.
        state["calls"].append(list(message.tokens))
        responses = []
        for ok, err in zip(state["responses"], state["errors"]):
            r = MagicMock()
            r.success = ok
            r.exception = err
            responses.append(r)
        batch = MagicMock()
        batch.responses = responses
        batch.success_count = sum(1 for ok in state["responses"] if ok)
        return batch

    monkeypatch.setattr(
        "app.domain.notification.service.fcm.messaging.send_each_for_multicast",
        _fake_send_each_for_multicast,
    )
    monkeypatch.setattr(
        "app.domain.notification.service.fcm.get_fcm_app",
        lambda: MagicMock(name="fcm-app"),
    )

    return type("FcmStub", (), {
        "set_responses": staticmethod(_set_responses),
        "calls": state["calls"],
    })()


# ──────────────────── 검증 helper ────────────────────

async def fetch_user(session_factory, user_id: str) -> User | None:
    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.user_id == user_id)
        )
        return result.scalar_one_or_none()


async def fetch_member(session_factory, room_id: str, user_id: str) -> ChatRoomMember | None:
    async with session_factory() as session:
        return await session.get(ChatRoomMember, (room_id, user_id))


async def fetch_tokens_by_user(session_factory, user_id: str) -> list[FcmToken]:
    async with session_factory() as session:
        result = await session.execute(
            select(FcmToken).where(FcmToken.user_id == user_id)
        )
        return list(result.scalars().all())


# ──────────────────── 인박스 (Mongo) — opt-in fixtures ────────────────────

@pytest_asyncio.fixture
async def mongo_db():
    """`inbox` 컬렉션 초기화 + beanie init.

    매 테스트 전/후 컬렉션 drop — 인덱스도 함께 사라지므로 init_beanie 가 재생성. partial
    unique 인덱스가 실 mongo 에 적용되어 dedup 흐름이 검증되는 것이 핵심.
    """
    from beanie import init_beanie

    url = _require_mongo_url()
    client = AsyncIOMotorClient(url, tz_aware=True)
    db = client.get_default_database()

    await db.inbox.drop()
    await init_beanie(database=db, document_models=[InboxItem])

    try:
        yield db
    finally:
        await db.inbox.drop()
        client.close()


@pytest.fixture
def inbox_service(mongo_db) -> InboxService:
    """인박스 서비스 — stateless. 매 테스트마다 fresh 인스턴스로 충분."""
    return InboxService()
