"""MessageHistoryService 통합 테스트 (PHASE_2 #4).

실제 Mongo 에 여러 건의 메시지를 쓴 뒤 `before_server_seq` / `after_server_seq`
페이징 규약이 정확히 동작하는지 검증. catch-up 경로(`after`) 가 ASC 로 정렬되어
next_cursor 를 따라가며 누락 없이 전부 내려오는지도 확인.
"""
import pytest_asyncio
import pytest
from datetime import datetime, timedelta, timezone

from app.domain.friend.model.friendship import Friendship, FriendshipStatus
from app.domain.chat.service.room import RoomService
from app.domain.chat.service.message_history import MessageHistoryService
from app.domain.chat.service.message import MessageService
from app.domain.chat.model.chat_message import MessageType
from app.domain.chat.dto.message import MessageListData


pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def seed_friendship(session_factory):
    async def _seed(user_a: str, user_b: str) -> None:
        async with session_factory() as s:
            s.add(Friendship(
                requester_id=user_a,
                addressee_id=user_b,
                status=FriendshipStatus.ACCEPTED,
            ))
            await s.commit()
    return _seed


@pytest_asyncio.fixture
async def room_with_messages(
    uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
    patch_external_clients,
):
    """그룹 방 + 실제 `send_message` 호출로 N 건 적재한 픽스처.

    방 생성 시 `system message (created)` 가 자동 기록되므로 그 뒤에 text 메시지 N 건.
    반환: (room_id, user_a, user_b, text_seqs) — text 메시지의 server_seq 리스트 (오름차순)
    """
    a, b, _ = await seed_users(3)
    await seed_friendship(a, b)

    room_svc = RoomService(
        uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
    )
    room = await room_svc.create_group_room(me_id=a, title="hist", member_ids=[b])
    room_id = room.chat_room_id

    text_seqs: list[int] = []
    for i in range(10):
        ack = await message_service.send_message(
            sender_user_id=a,
            sender_session_id=f"WS_A_{i}",
            room_id=room_id,
            client_msg_id=f"cm-{i}",
            msg_type=MessageType.TEXT,
            content=f"msg {i}",
        )
        text_seqs.append(ack.server_seq)

    return room_id, a, b, text_seqs


# ──────────────────────────────────────────────────────────────────
# find_messages_before (위로 스크롤)
# ──────────────────────────────────────────────────────────────────

class TestFindMessagesBeforeFlow:
    async def test_paginates_desc_with_has_more(
        self, uow, room_with_messages, patch_external_clients,
    ):
        room_id, a, b, text_seqs = room_with_messages
        history = MessageHistoryService(uow=uow)

        # 첫 페이지 — 가장 최근 5건
        page1: MessageListData = await history.find_messages_before(
            me_id=a, room_id=room_id, before_server_seq=10_000_000, limit=5,
        )
        assert len(page1.messages) == 5
        assert page1.has_more is True
        # DESC 정렬 — 첫 페이지 마지막 메시지가 다음 커서
        assert page1.next_cursor == page1.messages[-1].server_seq
        # 최신순 확인 (내림차순)
        seqs1 = [m.server_seq for m in page1.messages]
        assert seqs1 == sorted(seqs1, reverse=True)

        # 다음 페이지 — next_cursor 로 이어서
        page2 = await history.find_messages_before(
            me_id=a, room_id=room_id, before_server_seq=page1.next_cursor, limit=5,
        )
        # text 10건 + system 1건 (created) = 총 11건. 5 찍고 다음 5 + system 1 = 6 이 남음
        assert len(page2.messages) <= 6
        # 최종 페이지에 도달
        if page2.has_more:
            # 6건 보다 적게 받은 경우 — 다음 호출에 반드시 소진
            page3 = await history.find_messages_before(
                me_id=a, room_id=room_id, before_server_seq=page2.next_cursor, limit=10,
            )
            assert page3.has_more is False

        # 두 페이지 합집합이 중복 없이 원본 seqs(+system) 를 포괄
        combined = [m.server_seq for m in (page1.messages + page2.messages)]
        assert len(combined) == len(set(combined)), "페이지 간 중복 발생"


    async def test_empty_room_returns_empty_page(
        self, uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
        patch_external_clients,
    ):
        a, b, _ = await seed_users(3)
        await seed_friendship(a, b)
        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await room_svc.create_group_room(me_id=a, title="empty", member_ids=[b])

        history = MessageHistoryService(uow=uow)
        # 방 생성 직후라 system message 1 건만 있음 (seq=1). seq<0 이면 빈 배열
        result = await history.find_messages_before(
            me_id=a, room_id=room.chat_room_id, before_server_seq=0, limit=10,
        )
        assert result.messages == []
        assert result.has_more is False
        assert result.next_cursor is None


# ──────────────────────────────────────────────────────────────────
# find_messages_after (catch-up)
# ──────────────────────────────────────────────────────────────────

class TestFindMessagesAfterFlow:
    async def test_catch_up_returns_ascending_up_to_limit(
        self, uow, room_with_messages, patch_external_clients,
    ):
        room_id, a, _, text_seqs = room_with_messages
        history = MessageHistoryService(uow=uow)

        # after=0 → 전체 히스토리 (system + text) 중 limit 만큼 ASC
        page1 = await history.find_messages_after(
            me_id=a, room_id=room_id, after_server_seq=0, limit=5,
        )
        assert len(page1.messages) == 5
        seqs1 = [m.server_seq for m in page1.messages]
        assert seqs1 == sorted(seqs1)  # ASC
        assert page1.has_more is True
        assert page1.next_cursor == seqs1[-1]

        # 다음 catch-up — next_cursor 이어서
        collected = list(seqs1)
        cursor = page1.next_cursor
        safety = 0
        while cursor is not None and safety < 5:
            nxt = await history.find_messages_after(
                me_id=a, room_id=room_id, after_server_seq=cursor, limit=5,
            )
            collected.extend(m.server_seq for m in nxt.messages)
            cursor = nxt.next_cursor
            safety += 1

        # 누락 없이 전체 seq 포괄 (최소한 text 10건은 전부 포함되어야 함)
        for seq in text_seqs:
            assert seq in collected, f"catch-up 에서 seq={seq} 누락"
        # 중복 없음
        assert len(collected) == len(set(collected))


    async def test_after_beyond_max_returns_empty(
        self, uow, room_with_messages, patch_external_clients,
    ):
        """catch-up 이 완료된 상태에서 다시 호출 → 빈 배열 + has_more=False."""
        room_id, a, _, text_seqs = room_with_messages
        history = MessageHistoryService(uow=uow)

        result = await history.find_messages_after(
            me_id=a, room_id=room_id, after_server_seq=max(text_seqs) + 100, limit=200,
        )
        assert result.messages == []
        assert result.has_more is False
        assert result.next_cursor is None


# ──────────────────────────────────────────────────────────────────
# 권한 체크
# ──────────────────────────────────────────────────────────────────

class TestPermissionFlow:
    async def test_non_member_cannot_read(
        self, uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
        patch_external_clients,
    ):
        a, b, c = await seed_users(3)
        await seed_friendship(a, b)
        # c 는 방에 들어있지 않음

        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await room_svc.create_group_room(me_id=a, title="T", member_ids=[b])

        history = MessageHistoryService(uow=uow)
        with pytest.raises(PermissionError):
            await history.find_messages_before(
                me_id=c, room_id=room.chat_room_id, before_server_seq=999, limit=10,
            )
        with pytest.raises(PermissionError):
            await history.find_messages_after(
                me_id=c, room_id=room.chat_room_id, after_server_seq=0, limit=10,
            )


    async def test_left_member_cannot_read(
        self, uow, seed_users, seed_friendship, chat_fanout_stub, message_service,
        patch_external_clients,
    ):
        a, b, _ = await seed_users(3)
        await seed_friendship(a, b)
        room_svc = RoomService(
            uow=uow, fanout_service=chat_fanout_stub, message_service=message_service,
        )
        room = await room_svc.create_group_room(me_id=a, title="T", member_ids=[b])
        await room_svc.leave_room(me_id=b, room_id=room.chat_room_id)

        history = MessageHistoryService(uow=uow)
        with pytest.raises(PermissionError):
            await history.find_messages_before(
                me_id=b, room_id=room.chat_room_id, before_server_seq=999, limit=10,
            )


# ──────────────────────────────────────────────────────────────────
# list_rooms (catch-up 기반 재진입 시 방별 last_message_server_seq 필요)
# ──────────────────────────────────────────────────────────────────

class TestListRoomsFlow:
    async def test_includes_last_message_preview_and_unread(
        self, uow, room_with_messages, redis_hot, patch_external_clients,
    ):
        room_id, a, b, text_seqs = room_with_messages
        history = MessageHistoryService(uow=uow)

        result = await history.list_rooms(me_id=a)
        assert len(result.items) == 1
        item = result.items[0]
        assert item.chat_room_id == room_id
        assert item.title == "hist"
        # 방 생성자 a 는 메시지 보낸 본인이라 unread 0
        assert item.unread_count == 0
        # last_message 는 마지막 text 메시지
        assert item.last_message is not None
        assert item.last_message.server_seq == max(text_seqs)
