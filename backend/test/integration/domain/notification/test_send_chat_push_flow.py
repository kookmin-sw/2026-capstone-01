"""send_chat_push 가드 체인 + 만료 토큰 정리 통합.

Firebase SDK 만 stub — DB(가드/조회/정리) 는 실 PostgreSQL 로 검증한다.
가드 체인:
    (1) 방별 — `chat_room_member.notification_muted IS NOT TRUE AND is_left=false`
    (2) 전역 — `users.notification_muted IS NOT TRUE`
    (3) 토큰 보유 — 0건이면 multicast skip
"""
from test.integration.domain.notification.conftest import fetch_tokens_by_user
import pytest
from firebase_admin import messaging


pytestmark = pytest.mark.integration


# ──────────────────── 정상 발송 ────────────────────

class TestHappyPath:
    async def test_all_pushable_users_get_multicast(
        self,
        fcm_service,
        seed_room_with_members,
        fcm_messaging_stub,
    ):
        """방 멤버 2명 모두 토큰 등록 + mute 없음 → multicast 1회, success_count = 토큰 합."""
        room_id, [user_a, user_b] = await seed_room_with_members(2)
        await fcm_service.register_token(user_id=user_a, token="tok-A1")
        await fcm_service.register_token(user_id=user_a, token="tok-A2")
        await fcm_service.register_token(user_id=user_b, token="tok-B1")
        fcm_messaging_stub.set_responses([True, True, True])

        sent = await fcm_service.send_chat_push(
            user_ids=[user_a, user_b],
            chat_room_id=room_id,
            sender_id="SYS",
            title="새 메시지",
            body="hi",
        )

        assert sent == 3
        assert len(fcm_messaging_stub.calls) == 1
        # 호출된 토큰 = 등록한 토큰 전체
        assert set(fcm_messaging_stub.calls[0]) == {"tok-A1", "tok-A2", "tok-B1"}


    async def test_empty_user_ids_skips_multicast(
        self, fcm_service, fcm_messaging_stub,
    ):
        """수신 후보 0명 — DB 쿼리도 multicast 호출도 발생하지 않음."""
        sent = await fcm_service.send_chat_push(
            user_ids=[],
            chat_room_id="CR_x", sender_id="SYS",
            title="t", body="b",
        )
        assert sent == 0
        assert fcm_messaging_stub.calls == []


# ──────────────────── 가드 체인 — 방별 mute ────────────────────

class TestRoomMuteGuard:
    async def test_room_muted_user_excluded(
        self, fcm_service, mute_service,
        seed_room_with_members, fcm_messaging_stub,
    ):
        """방별 mute=True 인 user 는 multicast 토큰 목록에서 제외."""
        room_id, [user_a, user_b] = await seed_room_with_members(2)
        await fcm_service.register_token(user_id=user_a, token="tok-A")
        await fcm_service.register_token(user_id=user_b, token="tok-B")

        await mute_service.set_room_mute(
            user_id=user_a, chat_room_id=room_id, muted=True,
        )
        fcm_messaging_stub.set_responses([True])  # B 만 통과

        sent = await fcm_service.send_chat_push(
            user_ids=[user_a, user_b],
            chat_room_id=room_id, sender_id="SYS",
            title="t", body="b",
        )

        assert sent == 1
        assert fcm_messaging_stub.calls[0] == ["tok-B"]


    async def test_left_member_excluded(
        self, fcm_service, session_factory,
        seed_room_with_members, fcm_messaging_stub,
    ):
        """`is_left=True` 인 멤버는 mute 와 무관하게 푸시 차단 — 탈퇴자 누수 방어."""
        room_id, [user_a, user_b] = await seed_room_with_members(2)
        await fcm_service.register_token(user_id=user_a, token="tok-A")
        await fcm_service.register_token(user_id=user_b, token="tok-B")

        async with session_factory() as session:
            from app.domain.chat.model.chat_room_member import ChatRoomMember
            member = await session.get(ChatRoomMember, (room_id, user_a))
            member.is_left = True
            await session.commit()

        fcm_messaging_stub.set_responses([True])

        sent = await fcm_service.send_chat_push(
            user_ids=[user_a, user_b],
            chat_room_id=room_id, sender_id="SYS",
            title="t", body="b",
        )

        assert sent == 1
        assert fcm_messaging_stub.calls[0] == ["tok-B"]


# ──────────────────── 가드 체인 — 전역 mute ────────────────────

class TestGlobalMuteGuard:
    async def test_globally_muted_user_excluded(
        self, fcm_service, mute_service,
        seed_room_with_members, fcm_messaging_stub,
    ):
        """전역 mute=True 인 user 는 어느 방의 푸시든 제외."""
        room_id, [user_a, user_b] = await seed_room_with_members(2)
        await fcm_service.register_token(user_id=user_a, token="tok-A")
        await fcm_service.register_token(user_id=user_b, token="tok-B")

        await mute_service.set_global_mute(user_id=user_a, muted=True)
        fcm_messaging_stub.set_responses([True])

        sent = await fcm_service.send_chat_push(
            user_ids=[user_a, user_b],
            chat_room_id=room_id, sender_id="SYS",
            title="t", body="b",
        )

        assert sent == 1
        assert fcm_messaging_stub.calls[0] == ["tok-B"]


    async def test_all_muted_returns_zero_without_multicast(
        self, fcm_service, mute_service,
        seed_room_with_members, fcm_messaging_stub,
    ):
        """모두 차단된 케이스 — multicast 호출 자체가 일어나지 않음 (FCM 비용 0)."""
        room_id, [user_a, user_b] = await seed_room_with_members(2)
        await fcm_service.register_token(user_id=user_a, token="tok-A")
        await fcm_service.register_token(user_id=user_b, token="tok-B")
        await mute_service.set_global_mute(user_id=user_a, muted=True)
        await mute_service.set_global_mute(user_id=user_b, muted=True)

        sent = await fcm_service.send_chat_push(
            user_ids=[user_a, user_b],
            chat_room_id=room_id, sender_id="SYS",
            title="t", body="b",
        )

        assert sent == 0
        assert fcm_messaging_stub.calls == []


# ──────────────────── 가드 체인 — 토큰 보유 ────────────────────

class TestTokenGuard:
    async def test_no_tokens_skips_multicast(
        self, fcm_service, seed_room_with_members, fcm_messaging_stub,
    ):
        """가드 (1)(2) 통과해도 토큰 0건이면 multicast skip."""
        room_id, [user_a, user_b] = await seed_room_with_members(2)
        # 토큰 등록 안 함

        sent = await fcm_service.send_chat_push(
            user_ids=[user_a, user_b],
            chat_room_id=room_id, sender_id="SYS",
            title="t", body="b",
        )

        assert sent == 0
        assert fcm_messaging_stub.calls == []


# ──────────────────── 만료 토큰 자동 정리 ────────────────────

class TestUnregisteredTokenCleanup:
    async def test_unregistered_tokens_are_deleted(
        self,
        fcm_service,
        session_factory,
        seed_room_with_members,
        fcm_messaging_stub,
    ):
        """`UnregisteredError` (앱 삭제) 응답인 토큰은 같은 트랜잭션에서 bulk DELETE."""
        room_id, [user_a, user_b] = await seed_room_with_members(2)
        await fcm_service.register_token(user_id=user_a, token="tok-A1")
        await fcm_service.register_token(user_id=user_a, token="tok-A2")  # 이게 만료
        await fcm_service.register_token(user_id=user_b, token="tok-B1")

        # tokens 순서는 service 내부 SELECT 순서 — 다음 set_responses 가 멀티캐스트
        # 호출 시점의 토큰 순서와 1:1 대응되도록 set_responses 를 호출한 뒤
        # send_chat_push 에서 실제 순서로 검증.
        fcm_messaging_stub.set_responses(
            success=[True, False, True],
            errors=[None, messaging.UnregisteredError("expired"), None],
        )

        # service 내부 SELECT 순서를 모르므로, 한 번 send 후 호출된 토큰 순서를 확인하고
        # 응답을 그 순서에 맞춰 재구성 — 단순화 위해 호출 토큰 순서 기준으로 다시 set.
        # send_chat_push 한 번 호출에서 토큰 셋과 응답을 맞추기 위해,
        # 위 set_responses 가 [True, False, True] 으로 가정하고 manually 매핑한 시나리오:
        # FCM stub 은 토큰 순서대로 응답 매칭 → 가운데가 항상 만료됨.

        sent = await fcm_service.send_chat_push(
            user_ids=[user_a, user_b],
            chat_room_id=room_id, sender_id="SYS",
            title="t", body="b",
        )

        # 최소한 만료된 1건이 정리됐는지 확인 — 토큰 순서와 무관하게
        # `tok-A2` 가 만료라 가정한 위치에 따라 다를 수 있어, 실제 호출 시 토큰별 매핑은
        # stub 의 호출 토큰 리스트로 사후 검증.
        called_tokens = fcm_messaging_stub.calls[0]
        # 응답 [True, False, True] 매핑 — 가운데 토큰이 invalid 로 정리됨
        invalid_token = called_tokens[1]
        a_rows = await fetch_tokens_by_user(session_factory, user_a)
        b_rows = await fetch_tokens_by_user(session_factory, user_b)
        all_remaining = {r.token for r in a_rows + b_rows}
        assert invalid_token not in all_remaining
        assert sent == 2  # 성공 2건


    async def test_firebase_error_does_not_delete_tokens(
        self,
        fcm_service,
        session_factory,
        seed_room_with_members,
        fcm_messaging_stub,
        monkeypatch,
    ):
        """글로벌 FirebaseError(인증/네트워크) 는 토큰 정리 없이 0 반환 — 일시 장애와
        앱 삭제(UnregisteredError) 는 다르게 다뤄야 함."""
        from firebase_admin.exceptions import FirebaseError

        room_id, [user_a, _] = await seed_room_with_members(2)
        await fcm_service.register_token(user_id=user_a, token="tok-A")

        def _raise(*args, **kwargs):
            raise FirebaseError(code="UNAVAILABLE", message="boom")

        monkeypatch.setattr(
            "app.domain.notification.service.fcm.messaging.send_each_for_multicast",
            _raise,
        )

        sent = await fcm_service.send_chat_push(
            user_ids=[user_a],
            chat_room_id=room_id, sender_id="SYS",
            title="t", body="b",
        )

        assert sent == 0
        rows = await fetch_tokens_by_user(session_factory, user_a)
        assert len(rows) == 1  # 토큰 보존 — 일시 장애로 정리 안 함
