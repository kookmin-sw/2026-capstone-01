"""FcmService — 토큰 등록/해제 + bulk 푸시 가드 체인 단위 테스트."""
from test.unit.domain.notification.mock_factory import make_fcm_batch_response
import pytest
from firebase_admin.exceptions import FirebaseError
from firebase_admin import messaging
from datetime import datetime, timezone

from app.domain.notification.model.fcm_token import FcmToken


def _make_fcm_token(*, user_id: str, token: str, fcm_token_id: str = "FCM_x") -> FcmToken:
    """SQLAlchemy 모델을 DB 없이 인스턴스화 (PK/timestamps 직접 주입)."""
    t = FcmToken(user_id=user_id, token=token)
    t.fcm_token_id = fcm_token_id
    t.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t.updated_at = t.created_at
    return t


# ──────────────────────────────────────────────────────────────────
# register_token — 신규 / 동일 / 타user 분기
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRegisterToken:
    async def test_new_token_saves_and_returns_dto(
        self, service, fcm_token_repo_mock,
    ):
        fcm_token_repo_mock.find_by_token.return_value = None

        async def fake_save(t):
            t.fcm_token_id = "FCM_new"
            t.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
            return t
        fcm_token_repo_mock.save.side_effect = fake_save

        result = await service.register_token(user_id="USER_a", token="tok-1")

        fcm_token_repo_mock.save.assert_awaited_once()
        saved = fcm_token_repo_mock.save.await_args.args[0]
        assert saved.user_id == "USER_a"
        assert saved.token == "tok-1"

        assert result.fcm_token_id == "FCM_new"
        fcm_token_repo_mock.update.assert_not_awaited()


    async def test_same_user_same_token_is_noop(
        self, service, fcm_token_repo_mock,
    ):
        existing = _make_fcm_token(user_id="USER_a", token="tok-1")
        fcm_token_repo_mock.find_by_token.return_value = existing

        result = await service.register_token(user_id="USER_a", token="tok-1")

        assert result.fcm_token_id == existing.fcm_token_id
        fcm_token_repo_mock.save.assert_not_awaited()
        fcm_token_repo_mock.update.assert_not_awaited()


    async def test_different_user_same_token_updates_owner(
        self, service, fcm_token_repo_mock,
    ):
        """디바이스 계정 전환 — 같은 token 이 다른 user 로 등록될 때 owner 만 교체."""
        existing = _make_fcm_token(user_id="USER_old", token="tok-1")
        fcm_token_repo_mock.find_by_token.return_value = existing

        async def fake_update(t):
            return t
        fcm_token_repo_mock.update.side_effect = fake_update

        await service.register_token(user_id="USER_new", token="tok-1")

        assert existing.user_id == "USER_new"
        fcm_token_repo_mock.update.assert_awaited_once()
        fcm_token_repo_mock.save.assert_not_awaited()


# ──────────────────────────────────────────────────────────────────
# unregister_token — 본인 / 없음 / 타user (idempotent)
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestUnregisterToken:
    async def test_own_token_is_deleted(self, service, fcm_token_repo_mock):
        existing = _make_fcm_token(user_id="USER_a", token="tok")
        fcm_token_repo_mock.find_by_token.return_value = existing

        await service.unregister_token(user_id="USER_a", token="tok")

        fcm_token_repo_mock.delete.assert_awaited_once_with(existing)


    async def test_nonexistent_token_is_silent_noop(
        self, service, fcm_token_repo_mock,
    ):
        fcm_token_repo_mock.find_by_token.return_value = None

        # 예외 없이 정상 종료
        await service.unregister_token(user_id="USER_a", token="ghost")

        fcm_token_repo_mock.delete.assert_not_awaited()


    async def test_other_users_token_is_silent_noop(
        self, service, fcm_token_repo_mock,
    ):
        """타인 토큰 해제 시도 — 정보 누출 막기 위해 에러 던지지 않고 조용히 종료."""
        existing = _make_fcm_token(user_id="USER_other", token="tok")
        fcm_token_repo_mock.find_by_token.return_value = existing

        await service.unregister_token(user_id="USER_a", token="tok")

        fcm_token_repo_mock.delete.assert_not_awaited()


# ──────────────────────────────────────────────────────────────────
# send_chat_push — bulk 가드 체인
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSendChatPush:
    async def test_empty_user_ids_returns_zero_no_queries(
        self, service, chat_member_repo_mock, user_repo_mock,
        fcm_token_repo_mock, messaging_send_mock,
    ):
        result = await service.send_chat_push(
            user_ids=[],
            chat_room_id="CR_1", sender_id="USER_s",
            title="t", body="b",
        )

        assert result == 0
        chat_member_repo_mock.find_pushable_user_ids_in_room.assert_not_awaited()
        user_repo_mock.find_unmuted_user_ids.assert_not_awaited()
        fcm_token_repo_mock.find_by_user_ids.assert_not_awaited()
        messaging_send_mock.assert_not_called()


    async def test_all_room_muted_short_circuits(
        self, service, chat_member_repo_mock, user_repo_mock,
        fcm_token_repo_mock, messaging_send_mock,
    ):
        """방 mute / 비활성 멤버 가드에서 모두 걸러지면 그 다음 단계 미호출."""
        chat_member_repo_mock.find_pushable_user_ids_in_room.return_value = set()

        result = await service.send_chat_push(
            user_ids=["U_1", "U_2"],
            chat_room_id="CR_1", sender_id="USER_s",
            title="t", body="b",
        )

        assert result == 0
        user_repo_mock.find_unmuted_user_ids.assert_not_awaited()
        fcm_token_repo_mock.find_by_user_ids.assert_not_awaited()
        messaging_send_mock.assert_not_called()


    async def test_all_globally_muted_short_circuits(
        self, service, chat_member_repo_mock, user_repo_mock,
        fcm_token_repo_mock, messaging_send_mock,
    ):
        chat_member_repo_mock.find_pushable_user_ids_in_room.return_value = {"U_1"}
        user_repo_mock.find_unmuted_user_ids.return_value = set()

        result = await service.send_chat_push(
            user_ids=["U_1"],
            chat_room_id="CR_1", sender_id="USER_s",
            title="t", body="b",
        )

        assert result == 0
        fcm_token_repo_mock.find_by_user_ids.assert_not_awaited()
        messaging_send_mock.assert_not_called()


    async def test_no_tokens_returns_zero_no_fcm_call(
        self, service, chat_member_repo_mock, user_repo_mock,
        fcm_token_repo_mock, messaging_send_mock,
    ):
        chat_member_repo_mock.find_pushable_user_ids_in_room.return_value = {"U_1"}
        user_repo_mock.find_unmuted_user_ids.return_value = {"U_1"}
        fcm_token_repo_mock.find_by_user_ids.return_value = []

        result = await service.send_chat_push(
            user_ids=["U_1"],
            chat_room_id="CR_1", sender_id="USER_s",
            title="t", body="b",
        )

        assert result == 0
        messaging_send_mock.assert_not_called()


    async def test_happy_path_multicasts_with_all_tokens_and_correct_payload(
        self, service, chat_member_repo_mock, user_repo_mock,
        fcm_token_repo_mock, messaging_send_mock,
    ):
        """가드 통과 user 의 모든 디바이스 토큰을 한 multicast 로 발송 + 페이로드 검증."""
        chat_member_repo_mock.find_pushable_user_ids_in_room.return_value = {"U_1", "U_2"}
        user_repo_mock.find_unmuted_user_ids.return_value = {"U_1", "U_2"}
        # U_2 는 디바이스 2개 보유
        fcm_token_repo_mock.find_by_user_ids.return_value = [
            _make_fcm_token(user_id="U_1", token="tok-1"),
            _make_fcm_token(user_id="U_2", token="tok-2"),
            _make_fcm_token(user_id="U_2", token="tok-3"),
        ]
        messaging_send_mock.return_value = make_fcm_batch_response(
            success_results=[True, True, True],
        )

        result = await service.send_chat_push(
            user_ids=["U_1", "U_2"],
            chat_room_id="CR_1",
            sender_id="USER_s",
            title="새 메시지",
            body="hello",
        )

        assert result == 3
        messaging_send_mock.assert_called_once()

        msg_arg = messaging_send_mock.call_args.args[0]
        assert sorted(msg_arg.tokens) == ["tok-1", "tok-2", "tok-3"]
        assert msg_arg.notification.title == "새 메시지"
        assert msg_arg.notification.body == "hello"
        # 사용자 사양 데이터 페이로드 정확성
        assert msg_arg.data == {
            "type": "chat",
            "chatRoomId": "CR_1",
            "senderId": "USER_s",
            "url": "/chat/CR_1",
        }
        # 만료 정리 없음
        fcm_token_repo_mock.delete_by_tokens.assert_not_awaited()


    async def test_unregistered_tokens_get_bulk_cleaned_up(
        self, service, chat_member_repo_mock, user_repo_mock,
        fcm_token_repo_mock, messaging_send_mock,
    ):
        """앱 삭제로 UnregisteredError 받은 토큰만 bulk DELETE — 다른 실패는 보존."""
        chat_member_repo_mock.find_pushable_user_ids_in_room.return_value = {"U_1"}
        user_repo_mock.find_unmuted_user_ids.return_value = {"U_1"}
        fcm_token_repo_mock.find_by_user_ids.return_value = [
            _make_fcm_token(user_id="U_1", token="dead-tok"),
            _make_fcm_token(user_id="U_1", token="alive-tok"),
            _make_fcm_token(user_id="U_1", token="transient-tok"),
        ]
        # dead 는 UnregisteredError, transient 는 일반 FirebaseError(예: QuotaExceeded)
        messaging_send_mock.return_value = make_fcm_batch_response(
            success_results=[False, True, False],
            error_results=[
                messaging.UnregisteredError("uninstalled"),
                None,
                FirebaseError(code="QUOTA_EXCEEDED", message="rate"),
            ],
        )

        result = await service.send_chat_push(
            user_ids=["U_1"],
            chat_room_id="CR_1", sender_id="USER_s",
            title="t", body="b",
        )

        assert result == 1
        # UnregisteredError 토큰만 정리 (transient 는 건너뜀)
        fcm_token_repo_mock.delete_by_tokens.assert_awaited_once()
        deleted = fcm_token_repo_mock.delete_by_tokens.await_args.args[0]
        assert deleted == ["dead-tok"]


    async def test_global_firebase_error_returns_zero_no_cleanup(
        self, service, chat_member_repo_mock, user_repo_mock,
        fcm_token_repo_mock, messaging_send_mock,
    ):
        """multicast 자체가 FirebaseError 던지면 0 반환 + 토큰 정리 안 함 (transient 가능)."""
        chat_member_repo_mock.find_pushable_user_ids_in_room.return_value = {"U_1"}
        user_repo_mock.find_unmuted_user_ids.return_value = {"U_1"}
        fcm_token_repo_mock.find_by_user_ids.return_value = [
            _make_fcm_token(user_id="U_1", token="t1"),
        ]
        messaging_send_mock.side_effect = FirebaseError(
            code="UNAVAILABLE", message="server down",
        )

        result = await service.send_chat_push(
            user_ids=["U_1"],
            chat_room_id="CR_1", sender_id="USER_s",
            title="t", body="b",
        )

        assert result == 0
        fcm_token_repo_mock.delete_by_tokens.assert_not_awaited()
