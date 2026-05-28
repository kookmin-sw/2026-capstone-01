"""MessageHistoryService 단위 테스트 (PHASE_2 #4 테스트 커버리지 보강).

페이징 경계값 (`has_more` / `next_cursor`), 권한 체크, soft-delete 된 메시지 content
마스킹까지 검증. Mongo/Redis/RDB 는 전부 mock.
"""
from types import SimpleNamespace
import pytest
from datetime import datetime, timezone

from app.domain.chat.service.exception import ChatRoomNotFoundError
from app.domain.chat.model.chat_room import ChatRoomType


NOW = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)


def _mk_doc(
    message_id: str,
    server_seq: int,
    *,
    sender_id: str | None = "U_A",
    msg_type: str = "text",
    content=None,
    created_at: datetime = NOW,
    deleted_at: datetime | None = None,
    edited_at: datetime | None = None,
    chat_room_id: str = "CR_1",
) -> dict:
    return {
        "_id": message_id,
        "chat_room_id": chat_room_id,
        "server_seq": server_seq,
        "sender_id": sender_id,
        "type": msg_type,
        "content": "hi" if content is None else content,
        "created_at": created_at,
        "edited_at": edited_at,
        "deleted_at": deleted_at,
    }


def _mk_room(
    chat_room_id: str = "CR_1",
    *,
    type_: ChatRoomType = ChatRoomType.DIRECT,
    title: str | None = None,
    last_message_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        chat_room_id=chat_room_id,
        type=type_,
        title=title,
        last_message_id=last_message_id,
        last_message_server_seq=None,
        last_message_at=None,
        created_at=NOW,
        effective_last_at=NOW,
    )


# ──────────────────────────────────────────────────────────────────
# find_messages_before (위로 스크롤)
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestFindMessagesBefore:
    async def test_permission_error_when_not_active_member(
        self, service, chat_member_repo_mock,
    ):
        chat_member_repo_mock.is_active_member.return_value = False
        with pytest.raises(PermissionError):
            await service.find_messages_before(
                me_id="U_X", room_id="CR_1", before_server_seq=100, limit=10,
            )


    async def test_no_results(
        self, service, chat_member_repo_mock, message_repo_mock,
    ):
        chat_member_repo_mock.is_active_member.return_value = True
        message_repo_mock.find_before.return_value = []

        result = await service.find_messages_before(
            me_id="U_A", room_id="CR_1", before_server_seq=50, limit=10,
        )
        assert result.messages == []
        assert result.has_more is False
        assert result.next_cursor is None


    async def test_limit_exactly_no_more(
        self, service, chat_member_repo_mock, message_repo_mock,
    ):
        """limit=3 / 실제 조회 3건(limit+1=4 조회했으나 3개뿐) → has_more=False."""
        chat_member_repo_mock.is_active_member.return_value = True
        message_repo_mock.find_before.return_value = [
            _mk_doc("MSG_3", 3), _mk_doc("MSG_2", 2), _mk_doc("MSG_1", 1),
        ]

        result = await service.find_messages_before(
            me_id="U_A", room_id="CR_1", before_server_seq=10, limit=3,
        )
        assert len(result.messages) == 3
        assert result.has_more is False
        assert result.next_cursor is None


    async def test_limit_exceeded_has_more_and_cursor(
        self, service, chat_member_repo_mock, message_repo_mock,
    ):
        """limit=3, Mongo 에서 4건 반환 → has_more=True, next_cursor=3번째 seq (가장 오래된)."""
        chat_member_repo_mock.is_active_member.return_value = True
        message_repo_mock.find_before.return_value = [
            _mk_doc("MSG_6", 6), _mk_doc("MSG_5", 5),
            _mk_doc("MSG_4", 4), _mk_doc("MSG_3", 3),
        ]

        result = await service.find_messages_before(
            me_id="U_A", room_id="CR_1", before_server_seq=10, limit=3,
        )
        assert [m.server_seq for m in result.messages] == [6, 5, 4]
        assert result.has_more is True
        assert result.next_cursor == 4  # 마지막(=가장 오래된) seq


    async def test_deleted_message_content_is_masked(
        self, service, chat_member_repo_mock, message_repo_mock,
    ):
        chat_member_repo_mock.is_active_member.return_value = True
        message_repo_mock.find_before.return_value = [
            _mk_doc("MSG_1", 1, content="secret", deleted_at=NOW),
        ]

        result = await service.find_messages_before(
            me_id="U_A", room_id="CR_1", before_server_seq=10, limit=5,
        )
        assert result.messages[0].content is None  # 삭제된 메시지 마스킹
        assert result.messages[0].deleted_at == NOW


# ──────────────────────────────────────────────────────────────────
# find_messages_after (catch-up)
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestFindMessagesAfter:
    async def test_permission_error_when_not_active_member(
        self, service, chat_member_repo_mock,
    ):
        chat_member_repo_mock.is_active_member.return_value = False
        with pytest.raises(PermissionError):
            await service.find_messages_after(
                me_id="U_X", room_id="CR_1", after_server_seq=0, limit=200,
            )


    async def test_catch_up_ascending_with_has_more(
        self, service, chat_member_repo_mock, message_repo_mock,
    ):
        """after=0, limit=3, Mongo 에서 4건(ASC) 반환 → has_more=True, next_cursor=3번째 seq."""
        chat_member_repo_mock.is_active_member.return_value = True
        message_repo_mock.find_after.return_value = [
            _mk_doc("MSG_1", 1), _mk_doc("MSG_2", 2),
            _mk_doc("MSG_3", 3), _mk_doc("MSG_4", 4),
        ]

        result = await service.find_messages_after(
            me_id="U_A", room_id="CR_1", after_server_seq=0, limit=3,
        )
        assert [m.server_seq for m in result.messages] == [1, 2, 3]
        assert result.has_more is True
        assert result.next_cursor == 3  # 마지막(=가장 최신) seq — 클라는 다음 호출에 after=3


    async def test_no_more_messages_returns_empty(
        self, service, chat_member_repo_mock, message_repo_mock,
    ):
        """catch-up 완료 시 더 이상 메시지 없음 → 빈 배열 + has_more=False."""
        chat_member_repo_mock.is_active_member.return_value = True
        message_repo_mock.find_after.return_value = []

        result = await service.find_messages_after(
            me_id="U_A", room_id="CR_1", after_server_seq=999, limit=200,
        )
        assert result.messages == []
        assert result.has_more is False
        assert result.next_cursor is None


# ──────────────────────────────────────────────────────────────────
# list_rooms
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestListRooms:
    async def test_empty_when_no_rooms(
        self, service, chat_room_repo_mock, redis_mock,
    ):
        chat_room_repo_mock.find_rooms_of_user.return_value = []
        redis_mock.hgetall.return_value = {}

        result = await service.list_rooms(me_id="U_A")
        assert result.items == []
        assert result.next_cursor is None


    async def test_direct_room_with_peer_profile(
        self, service, chat_room_repo_mock, user_repo_mock, redis_mock,
        message_repo_mock,
    ):
        room = _mk_room(chat_room_id="CR_d", type_=ChatRoomType.DIRECT)
        chat_room_repo_mock.find_rooms_of_user.return_value = [(room, "U_B", None)]
        user_repo_mock.find_by_ids_with_profile.return_value = {
            "U_B": SimpleNamespace(
                user_id="U_B",
                detail=SimpleNamespace(
                    user_name="peer_name",
                    profile_image_url="https://cdn.example.com/u_b.jpg",
                ),
            ),
        }
        redis_mock.hgetall.return_value = {"CR_d": "3"}
        message_repo_mock.find_by_ids.return_value = {}

        result = await service.list_rooms(me_id="U_A")
        assert len(result.items) == 1
        item = result.items[0]
        assert item.type == ChatRoomType.DIRECT
        assert item.peer.user_id == "U_B"
        assert item.peer.user_name == "peer_name"
        assert item.peer.profile_image_url == "https://cdn.example.com/u_b.jpg"
        assert item.unread_count == 3
        assert item.last_message is None


    async def test_group_room_has_no_peer(
        self, service, chat_room_repo_mock, redis_mock, message_repo_mock,
    ):
        room = _mk_room(chat_room_id="CR_g", type_=ChatRoomType.GROUP, title="T")
        chat_room_repo_mock.find_rooms_of_user.return_value = [(room, None, None)]
        redis_mock.hgetall.return_value = {}
        message_repo_mock.find_by_ids.return_value = {}

        result = await service.list_rooms(me_id="U_A")
        assert result.items[0].type == ChatRoomType.GROUP
        assert result.items[0].title == "T"
        assert result.items[0].peer is None


    async def test_direct_peer_withdrawn_returns_null_profile(
        self, service, chat_room_repo_mock, redis_mock, message_repo_mock,
    ):
        """direct 방이지만 peer 가 탈퇴 → peer_user_id=None → peer 는 모두 None."""
        room = _mk_room(chat_room_id="CR_orphan", type_=ChatRoomType.DIRECT)
        chat_room_repo_mock.find_rooms_of_user.return_value = [(room, None, None)]
        redis_mock.hgetall.return_value = {}
        message_repo_mock.find_by_ids.return_value = {}

        result = await service.list_rooms(me_id="U_A")
        assert result.items[0].peer.user_id is None
        assert result.items[0].peer.user_name is None
        assert result.items[0].peer.profile_image_url is None


    async def test_last_message_preview_masks_deleted(
        self, service, chat_room_repo_mock, redis_mock, message_repo_mock,
    ):
        room = _mk_room(
            chat_room_id="CR_1", type_=ChatRoomType.GROUP, title="T",
            last_message_id="MSG_last",
        )
        chat_room_repo_mock.find_rooms_of_user.return_value = [(room, None, None)]
        redis_mock.hgetall.return_value = {}
        message_repo_mock.find_by_ids.return_value = {
            "MSG_last": _mk_doc(
                "MSG_last", 10, content="bye", deleted_at=NOW,
            )
        }

        result = await service.list_rooms(me_id="U_A")
        assert result.items[0].last_message is not None
        assert result.items[0].last_message.content is None  # 삭제 마스킹
        assert result.items[0].last_message.server_seq == 10


    async def test_last_message_preview_keeps_system_content_dict(
        self, service, chat_room_repo_mock, redis_mock, message_repo_mock,
    ):
        """system 메시지가 last_message 인 방 — content 의 dict 형태가 그대로 보존돼야 함.

        방 생성 직후처럼 system(`created`) 메시지가 가장 최근 메시지인 케이스.
        DTO 가 dict 를 그대로 들고 가야 라우터의 `LastMessagePreviewResponse` 가
        같은 모양으로 직렬화될 수 있다 (회귀 방지 — 과거 `Optional[str]` 로 좁혀져
        500 이 발생했음).
        """
        room = _mk_room(
            chat_room_id="CR_sys", type_=ChatRoomType.GROUP, title="sys",
            last_message_id="MSG_sys",
        )
        chat_room_repo_mock.find_rooms_of_user.return_value = [(room, None, None)]
        redis_mock.hgetall.return_value = {}
        payload = {"action": "created", "actor_id": "U_A"}
        message_repo_mock.find_by_ids.return_value = {
            "MSG_sys": _mk_doc(
                "MSG_sys", 1,
                sender_id=None,
                msg_type="system",
                content=payload,
            )
        }

        result = await service.list_rooms(me_id="U_A")
        item = result.items[0]
        assert item.last_message is not None
        assert item.last_message.type == "system"
        assert item.last_message.sender_id is None
        assert item.last_message.content == payload  # dict 보존 (str 변환 / drop 없음)


    async def test_last_message_preview_keeps_image_content_dict(
        self, service, chat_room_repo_mock, redis_mock, message_repo_mock,
    ):
        """image 메시지가 last_message 인 방 — dict content 가 그대로 보존."""
        room = _mk_room(
            chat_room_id="CR_img", type_=ChatRoomType.GROUP, title="img",
            last_message_id="MSG_img",
        )
        chat_room_repo_mock.find_rooms_of_user.return_value = [(room, None, None)]
        redis_mock.hgetall.return_value = {}
        payload = {"url": "https://cdn.example.com/p.jpg", "name": "p.jpg"}
        message_repo_mock.find_by_ids.return_value = {
            "MSG_img": _mk_doc(
                "MSG_img", 5,
                sender_id="U_A",
                msg_type="image",
                content=payload,
            )
        }

        result = await service.list_rooms(me_id="U_A")
        item = result.items[0]
        assert item.last_message is not None
        assert item.last_message.type == "image"
        assert item.last_message.content == payload


    async def test_notification_muted_true_exposed_as_true(
        self, service, chat_room_repo_mock, redis_mock, message_repo_mock,
    ):
        """방별 mute=True 인 row 는 응답에 그대로 True 노출."""
        room = _mk_room(chat_room_id="CR_m", type_=ChatRoomType.GROUP, title="T")
        chat_room_repo_mock.find_rooms_of_user.return_value = [(room, None, True)]
        redis_mock.hgetall.return_value = {}
        message_repo_mock.find_by_ids.return_value = {}

        result = await service.list_rooms(me_id="U_A")
        assert result.items[0].notification_muted is True


    async def test_notification_muted_null_normalizes_to_false(
        self, service, chat_room_repo_mock, redis_mock, message_repo_mock,
    ):
        """DB NULL (기본 unmuted) → 응답에선 False 로 coerce — 클라가 null 분기 안 해도 됨."""
        room = _mk_room(chat_room_id="CR_u", type_=ChatRoomType.GROUP, title="T")
        chat_room_repo_mock.find_rooms_of_user.return_value = [(room, None, None)]
        redis_mock.hgetall.return_value = {}
        message_repo_mock.find_by_ids.return_value = {}

        result = await service.list_rooms(me_id="U_A")
        assert result.items[0].notification_muted is False


    async def test_notification_muted_false_treated_as_unmuted(
        self, service, chat_room_repo_mock, redis_mock, message_repo_mock,
    ):
        """레거시/이상치로 False 가 들어와도 `is True` 비교라 False 로 노출 (방어)."""
        room = _mk_room(chat_room_id="CR_f", type_=ChatRoomType.GROUP, title="T")
        chat_room_repo_mock.find_rooms_of_user.return_value = [(room, None, False)]
        redis_mock.hgetall.return_value = {}
        message_repo_mock.find_by_ids.return_value = {}

        result = await service.list_rooms(me_id="U_A")
        assert result.items[0].notification_muted is False


# ──────────────────────────────────────────────────────────────────
# get_room — 단건 방 조회 (권한 체크 + mute 노출 통합)
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetRoom:
    """`get_room` 은 `member_repo.find()` 한 번으로 권한 체크 + mute 획득을 통합한다.
    `is_active_member` 의 boolean 단순 체크가 mute 정보를 누락하므로 `find()` 로 갈아끼웠고,
    이 변경의 정합성을 보장하는 테스트들이다.
    """

    async def test_room_not_found_raises(self, service, chat_room_repo_mock):
        chat_room_repo_mock.find_by_id.return_value = None
        with pytest.raises(ChatRoomNotFoundError):
            await service.get_room(me_id="U_A", room_id="CR_X")


    async def test_non_member_raises_permission_error(
        self, service, chat_room_repo_mock, chat_member_repo_mock,
    ):
        """member row 자체가 없는 케이스 (가입 이력 없음)."""
        room = _mk_room(chat_room_id="CR_1", type_=ChatRoomType.GROUP, title="T")
        chat_room_repo_mock.find_by_id.return_value = room
        chat_member_repo_mock.find.return_value = None

        with pytest.raises(PermissionError):
            await service.get_room(me_id="U_A", room_id="CR_1")


    async def test_left_member_raises_permission_error(
        self, service, chat_room_repo_mock, chat_member_repo_mock,
    ):
        """탈퇴자 (`is_left=True`) 도 비멤버와 동일하게 거절 — `find()` 통합 후에도 보장."""
        room = _mk_room(chat_room_id="CR_1", type_=ChatRoomType.GROUP, title="T")
        chat_room_repo_mock.find_by_id.return_value = room
        chat_member_repo_mock.find.return_value = SimpleNamespace(
            chat_room_id="CR_1", user_id="U_A", is_left=True, notification_muted=None,
        )

        with pytest.raises(PermissionError):
            await service.get_room(me_id="U_A", room_id="CR_1")


    async def test_active_member_with_mute_true_exposes_true(
        self, service, chat_room_repo_mock, chat_member_repo_mock,
        redis_mock, message_repo_mock,
    ):
        """활성 멤버 + mute=True → 응답에 True 노출 + last_message/peer 정상."""
        room = _mk_room(chat_room_id="CR_g", type_=ChatRoomType.GROUP, title="T")
        chat_room_repo_mock.find_by_id.return_value = room
        chat_member_repo_mock.find.return_value = SimpleNamespace(
            chat_room_id="CR_g", user_id="U_A", is_left=False, notification_muted=True,
        )
        redis_mock.hget.return_value = None
        message_repo_mock.find_by_id.return_value = None

        result = await service.get_room(me_id="U_A", room_id="CR_g")
        assert result.notification_muted is True
        assert result.title == "T"
        assert result.peer is None  # group


    async def test_active_member_with_mute_null_exposes_false(
        self, service, chat_room_repo_mock, chat_member_repo_mock,
        redis_mock, message_repo_mock,
    ):
        room = _mk_room(chat_room_id="CR_g", type_=ChatRoomType.GROUP, title="T")
        chat_room_repo_mock.find_by_id.return_value = room
        chat_member_repo_mock.find.return_value = SimpleNamespace(
            chat_room_id="CR_g", user_id="U_A", is_left=False, notification_muted=None,
        )
        redis_mock.hget.return_value = None
        message_repo_mock.find_by_id.return_value = None

        result = await service.get_room(me_id="U_A", room_id="CR_g")
        assert result.notification_muted is False


    async def test_direct_room_loads_peer_profile(
        self, service, chat_room_repo_mock, chat_member_repo_mock,
        user_repo_mock, redis_mock, message_repo_mock,
    ):
        """1:1 방 — peer_user_id 파생 + 프로필 로드 + mute 노출까지 한 흐름에서 검증."""
        room = SimpleNamespace(
            chat_room_id="CR_d",
            type=ChatRoomType.DIRECT,
            title=None,
            direct_user_a_id="U_A",
            direct_user_b_id="U_B",
            last_message_id=None,
            last_message_server_seq=None,
            last_message_at=None,
            created_at=NOW,
            effective_last_at=NOW,
        )
        chat_room_repo_mock.find_by_id.return_value = room
        chat_member_repo_mock.find.return_value = SimpleNamespace(
            chat_room_id="CR_d", user_id="U_A", is_left=False, notification_muted=None,
        )
        user_repo_mock.find_by_id_with_profile.return_value = SimpleNamespace(
            user_id="U_B",
            detail=SimpleNamespace(user_name="peer", profile_image_url=None),
        )
        redis_mock.hget.return_value = b"7"

        result = await service.get_room(me_id="U_A", room_id="CR_d")
        assert result.type == ChatRoomType.DIRECT
        assert result.peer.user_id == "U_B"
        assert result.peer.user_name == "peer"
        assert result.unread_count == 7
        assert result.notification_muted is False


# ──────────────────────────────────────────────────────────────────
# get_unread_counts
# ──────────────────────────────────────────────────────────────────

def _mk_user(
    user_id: str,
    user_name: str = "u",
    profile_image_url: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=user_id,
        detail=SimpleNamespace(
            user_name=user_name,
            profile_image_url=profile_image_url,
        ),
    )


# ──────────────────────────────────────────────────────────────────
# list_room_members (그룹 방 참여자 목록)
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestListRoomMembers:
    async def test_room_not_found_raises(self, service, chat_room_repo_mock):
        chat_room_repo_mock.find_by_id.return_value = None
        with pytest.raises(ChatRoomNotFoundError):
            await service.list_room_members(me_id="U_A", room_id="CR_X")


    async def test_non_member_raises(
        self, service, chat_room_repo_mock, chat_member_repo_mock,
    ):
        chat_room_repo_mock.find_by_id.return_value = _mk_room(type_=ChatRoomType.GROUP)
        chat_member_repo_mock.is_active_member.return_value = False
        with pytest.raises(PermissionError):
            await service.list_room_members(me_id="U_X", room_id="CR_1")


    async def test_direct_room_raises(
        self, service, chat_room_repo_mock, chat_member_repo_mock,
    ):
        chat_room_repo_mock.find_by_id.return_value = _mk_room(type_=ChatRoomType.DIRECT)
        chat_member_repo_mock.is_active_member.return_value = True
        with pytest.raises(ValueError, match="그룹 방"):
            await service.list_room_members(me_id="U_A", room_id="CR_d")


    async def test_returns_active_members_with_profile(
        self, service, chat_room_repo_mock, chat_member_repo_mock,
    ):
        chat_room_repo_mock.find_by_id.return_value = _mk_room(type_=ChatRoomType.GROUP)
        chat_member_repo_mock.is_active_member.return_value = True
        chat_member_repo_mock.find_active_member_users.return_value = [
            _mk_user("U_A", "alice", "https://cdn.example.com/a.jpg"),
            _mk_user("U_B", "bob", None),
        ]

        result = await service.list_room_members(me_id="U_A", room_id="CR_g")

        assert len(result.items) == 2
        assert result.items[0].user_id == "U_A"
        assert result.items[0].user_name == "alice"
        assert result.items[0].profile_image_url == "https://cdn.example.com/a.jpg"
        assert result.items[1].user_id == "U_B"
        assert result.items[1].profile_image_url is None


# ──────────────────────────────────────────────────────────────────
# list_invitable_friends (그룹 방 초대 가능 친구 목록)
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestListInvitableFriends:
    async def test_room_not_found_raises(self, service, chat_room_repo_mock):
        chat_room_repo_mock.find_by_id.return_value = None
        with pytest.raises(ChatRoomNotFoundError):
            await service.list_invitable_friends(me_id="U_A", room_id="CR_X")


    async def test_non_member_raises(
        self, service, chat_room_repo_mock, chat_member_repo_mock,
    ):
        chat_room_repo_mock.find_by_id.return_value = _mk_room(type_=ChatRoomType.GROUP)
        chat_member_repo_mock.is_active_member.return_value = False
        with pytest.raises(PermissionError):
            await service.list_invitable_friends(me_id="U_X", room_id="CR_g")


    async def test_direct_room_raises(
        self, service, chat_room_repo_mock, chat_member_repo_mock,
    ):
        chat_room_repo_mock.find_by_id.return_value = _mk_room(type_=ChatRoomType.DIRECT)
        chat_member_repo_mock.is_active_member.return_value = True
        with pytest.raises(ValueError, match="그룹 방"):
            await service.list_invitable_friends(me_id="U_A", room_id="CR_d")


    async def test_no_friends_returns_empty(
        self, service, chat_room_repo_mock, chat_member_repo_mock,
        friendship_repo_mock,
    ):
        chat_room_repo_mock.find_by_id.return_value = _mk_room(type_=ChatRoomType.GROUP)
        chat_member_repo_mock.is_active_member.return_value = True
        friendship_repo_mock.find_accepted_friend_ids.return_value = set()

        result = await service.list_invitable_friends(me_id="U_A", room_id="CR_g")
        assert result.items == []


    async def test_all_friends_already_in_room_returns_empty(
        self, service, chat_room_repo_mock, chat_member_repo_mock,
        friendship_repo_mock,
    ):
        chat_room_repo_mock.find_by_id.return_value = _mk_room(type_=ChatRoomType.GROUP)
        chat_member_repo_mock.is_active_member.return_value = True
        friendship_repo_mock.find_accepted_friend_ids.return_value = {"U_B", "U_C"}
        chat_member_repo_mock.find_active_member_ids.return_value = ["U_A", "U_B", "U_C"]

        result = await service.list_invitable_friends(me_id="U_A", room_id="CR_g")
        assert result.items == []


    async def test_returns_friends_not_in_room_with_profile(
        self, service, chat_room_repo_mock, chat_member_repo_mock,
        friendship_repo_mock, user_repo_mock,
    ):
        chat_room_repo_mock.find_by_id.return_value = _mk_room(type_=ChatRoomType.GROUP)
        chat_member_repo_mock.is_active_member.return_value = True
        friendship_repo_mock.find_accepted_friend_ids.return_value = {"U_B", "U_C", "U_D"}
        # U_C 만 이미 방 멤버 → U_B, U_D 가 초대 가능
        chat_member_repo_mock.find_active_member_ids.return_value = ["U_A", "U_C"]
        user_repo_mock.find_by_ids_with_profile.return_value = {
            "U_B": _mk_user("U_B", "bob", "https://cdn.example.com/b.jpg"),
            "U_D": _mk_user("U_D", "dave", None),
        }

        result = await service.list_invitable_friends(me_id="U_A", room_id="CR_g")

        # 정렬은 user_id ASC (서비스가 sorted 사용)
        assert [m.user_id for m in result.items] == ["U_B", "U_D"]
        assert result.items[0].profile_image_url == "https://cdn.example.com/b.jpg"
        assert result.items[1].profile_image_url is None
        # 호출 인자도 sorted invitable_ids
        user_repo_mock.find_by_ids_with_profile.assert_awaited_once_with(["U_B", "U_D"])


@pytest.mark.unit
class TestGetUnreadCounts:
    async def test_maps_hgetall_to_int_dict(self, service, redis_mock):
        redis_mock.hgetall.return_value = {"CR_1": "5", "CR_2": "0"}
        result = await service.get_unread_counts(me_id="U_A")
        assert result == {"CR_1": 5, "CR_2": 0}


    async def test_empty_hash_returns_empty_dict(self, service, redis_mock):
        redis_mock.hgetall.return_value = {}
        result = await service.get_unread_counts(me_id="U_A")
        assert result == {}
