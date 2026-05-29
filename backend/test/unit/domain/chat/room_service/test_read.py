"""RoomService.mark_read 단위 테스트 (PHASE_2 #3).

read op 는 **GREATEST 로 regress 방지**, **unread=0 리셋**, **read_ack 발신 세션
직송 + read 이벤트 방 브로드캐스트** 세 가지를 수행. mock 레벨에서 각 단계 호출과
payload 를 정확히 검증한다.
"""
from test.unit.domain.chat.room_service.model_factory import ChatRoomFactory
import pytest

from app.domain.chat.service.exception import ChatRoomNotFoundError
from app.domain.chat.model.chat_room import ChatRoomType


@pytest.mark.unit
class TestMarkRead:
    async def test_raises_on_zero_or_negative_seq(self, service):
        with pytest.raises(ValueError, match="1 이상"):
            await service.mark_read(
                me_id="U_A", me_session_id="WS_A", room_id="CR_G",
                up_to_server_seq=0,
            )
        with pytest.raises(ValueError, match="1 이상"):
            await service.mark_read(
                me_id="U_A", me_session_id="WS_A", room_id="CR_G",
                up_to_server_seq=-1,
            )


    async def test_raises_room_not_found(
        self, service, chat_room_repo_mock,
    ):
        chat_room_repo_mock.find_by_id.return_value = None
        with pytest.raises(ChatRoomNotFoundError):
            await service.mark_read(
                me_id="U_A", me_session_id="WS_A", room_id="CR_X",
                up_to_server_seq=5,
            )


    async def test_non_member_raises_permission_error(
        self, service, chat_room_repo_mock, chat_member_repo_mock,
    ):
        chat_room_repo_mock.find_by_id.return_value = ChatRoomFactory.create(
            type_=ChatRoomType.GROUP,
        )
        chat_member_repo_mock.mark_read.return_value = None  # 활성 멤버 아님
        with pytest.raises(PermissionError):
            await service.mark_read(
                me_id="U_A", me_session_id="WS_A", room_id="CR_G",
                up_to_server_seq=5,
            )


    async def test_successful_mark_read_resets_unread_and_fans_out(
        self, service, chat_room_repo_mock, chat_member_repo_mock,
        redis_mock, fanout_mock,
    ):
        chat_room_repo_mock.find_by_id.return_value = ChatRoomFactory.create(
            chat_room_id="CR_G", type_=ChatRoomType.GROUP,
        )
        chat_member_repo_mock.mark_read.return_value = 7  # regress 적용 후 최종 seq

        result = await service.mark_read(
            me_id="U_A", me_session_id="WS_A", room_id="CR_G",
            up_to_server_seq=5,
        )

        assert result == 7

        # mark_read 가 repository 에 올바른 인자로 위임됐는지
        chat_member_repo_mock.mark_read.assert_awaited_once_with("CR_G", "U_A", 5)

        # Redis unread=0 리셋 (redis.hset 직접 호출)
        redis_mock.hset.assert_awaited_once()
        args = redis_mock.hset.call_args.args
        assert args[0] == "unread:U_A"
        assert args[1] == "CR_G"
        assert args[2] == 0

        # read_ack 발신 세션 직송
        fanout_mock.fan_out_to_session.assert_awaited_once()
        sess_args = fanout_mock.fan_out_to_session.call_args.args
        assert sess_args[0] == "WS_A"
        assert sess_args[1] == {
            "type": "read_ack", "room_id": "CR_G", "up_to_server_seq": 7,
        }

        # 방에 read 이벤트 브로드캐스트 (sender_session_id 로 자기 에코 차단)
        fanout_mock.fan_out_to_room.assert_awaited_once()
        room_args = fanout_mock.fan_out_to_room.call_args.args
        assert room_args[0] == "CR_G"
        assert room_args[1] == {
            "type": "read",
            "user_id": "U_A",
            "sender_session_id": "WS_A",
            "up_to_server_seq": 7,
        }


    async def test_returns_repository_final_seq_even_when_regressed(
        self, service, chat_room_repo_mock, chat_member_repo_mock,
    ):
        """클라가 과거 seq 를 보내도 GREATEST 로 올라간 값이 그대로 돌아온다 (regress 무시)."""
        chat_room_repo_mock.find_by_id.return_value = ChatRoomFactory.create(
            type_=ChatRoomType.GROUP,
        )
        chat_member_repo_mock.mark_read.return_value = 20  # 이미 20 까지 읽은 상태

        result = await service.mark_read(
            me_id="U_A", me_session_id="WS_A", room_id="CR_G",
            up_to_server_seq=5,
        )
        assert result == 20
