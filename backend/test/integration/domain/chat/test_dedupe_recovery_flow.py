"""dedupe 키 lifecycle 통합 검증 — Mongo 일시 장애 시 영구 잔존하지 않음.

regression (#1):
    이전 구현은 Mongo insert 단계에서 `except DuplicateKeyError` 만 잡아
    ConnectionFailure 등 다른 Mongo 예외 시 dedupe 가 영구 잔존했다.
    같은 client_msg_id 가 DEDUPE_TTL(10분) 동안 차단되어 사용자가 재전송 불가.

이 통합 테스트는 실 Redis (dedupe DB) 에 키가 정확히 정리되는지, 그리고
재시도 경로가 end-to-end 로 동작하는지를 증명한다. 단위 테스트 (mock) 만으로는
"실제 Redis 키가 사라졌다" 를 보장하지 못함.
"""
from unittest.mock import AsyncMock, patch
import pytest
from pymongo.errors import ConnectionFailure

from app.domain.chat.service.message import MessageService
from app.domain.chat.model.chat_message import MessageType
from app.database.session import UnitOfWork
from app.core.chat.redis_key import dedupe_key


pytestmark = pytest.mark.integration


class TestDedupeRecoveryAfterMongoFailure:
    async def test_dedupe_key_cleared_after_mongo_connection_failure(
        self, session_factory, direct_room, chat_fanout_stub, chat_fcm_stub, redis_dedupe,
    ):
        """Mongo insert 가 ConnectionFailure → 실 Redis dedupe 키가 삭제됨.

        ChatMessageRepository.insert 를 patch 해 실 Mongo 호출 직전 ConnectionFailure
        를 던진다. except 블록의 redis_dedupe.delete 가 실 Redis 에 적용되는지 확인.
        """
        room_id, user_a, _ = direct_room
        cmid = "cm-mongo-conn-fail"

        with patch(
            "app.domain.chat.repository.chat_message.ChatMessageRepository.insert",
            new=AsyncMock(side_effect=ConnectionFailure("simulated network down")),
        ):
            uow = UnitOfWork(session=session_factory)
            svc = MessageService(uow=uow, fanout_service=chat_fanout_stub, fcm_service=chat_fcm_stub)
            with pytest.raises(ConnectionFailure):
                await svc.send_message(
                    sender_user_id=user_a,
                    sender_session_id="WS_A",
                    room_id=room_id,
                    client_msg_id=cmid,
                    msg_type=MessageType.TEXT,
                    content="x",
                )

        # 실 Redis 에서 dedupe 키가 사라졌는지 — 잔존하면 같은 cmid 재시도 불가
        key = dedupe_key(user_a, cmid)
        assert await redis_dedupe.exists(key) == 0, (
            f"Mongo 실패 후 dedupe 키 {key} 가 잔존 — 같은 client_msg_id 재시도 영구 차단"
        )


    async def test_retry_with_same_client_msg_id_succeeds_after_recovery(
        self, session_factory, direct_room, chat_fanout_stub, chat_fcm_stub,
        redis_dedupe, mongo_db,
    ):
        """장애 중 실패 → 장애 복구 후 같은 client_msg_id 로 재시도 → 정상 송신.

        end-to-end 회복 시나리오. 1차 실패 후 dedupe 가 정리되어야 2차 시도가
        SET NX 에서 first_time=True 로 통과할 수 있다.
        """
        room_id, user_a, _ = direct_room
        cmid = "cm-recover-flow"

        # 1차 — Mongo ConnectionFailure
        with patch(
            "app.domain.chat.repository.chat_message.ChatMessageRepository.insert",
            new=AsyncMock(side_effect=ConnectionFailure("transient")),
        ):
            uow1 = UnitOfWork(session=session_factory)
            svc1 = MessageService(uow=uow1, fanout_service=chat_fanout_stub, fcm_service=chat_fcm_stub)
            with pytest.raises(ConnectionFailure):
                await svc1.send_message(
                    sender_user_id=user_a,
                    sender_session_id="WS_A",
                    room_id=room_id,
                    client_msg_id=cmid,
                    msg_type=MessageType.TEXT,
                    content="원본",
                )

        # 2차 — Mongo 정상 복구. 같은 cmid 로 재시도 → 통과해야 함
        uow2 = UnitOfWork(session=session_factory)
        svc2 = MessageService(uow=uow2, fanout_service=chat_fanout_stub, fcm_service=chat_fcm_stub)
        ack = await svc2.send_message(
            sender_user_id=user_a,
            sender_session_id="WS_A",
            room_id=room_id,
            client_msg_id=cmid,
            msg_type=MessageType.TEXT,
            content="원본",
        )

        assert ack.client_msg_id == cmid
        assert ack.server_seq > 0

        # Mongo 에 정확히 1건 — 1차 실패는 저장되지 않았고 2차만 저장됨
        cursor = mongo_db.chat_message.find({"chat_room_id": room_id})
        docs = [doc async for doc in cursor]
        assert len(docs) == 1, (
            f"Mongo 저장 건수 이상 (기대 1, 실제 {len(docs)})"
        )
        assert docs[0]["server_seq"] == ack.server_seq
        assert docs[0]["sender_id"] == user_a


    async def test_happy_path_dedupe_persists_to_block_resend(
        self, session_factory, direct_room, chat_fanout_stub, chat_fcm_stub, redis_dedupe,
    ):
        """정상 송신 후 dedupe 는 TTL 동안 유지 — 같은 cmid 재전송 거절 확인.

        regression: try/except 가 너무 넓어져 정상 경로에서도 dedupe 를 풀어버리면
        dedupe 의 본래 목적 (네트워크 재시도 시 중복 메시지 차단) 이 무너짐.
        """
        room_id, user_a, _ = direct_room
        cmid = "cm-happy-block"

        uow1 = UnitOfWork(session=session_factory)
        svc1 = MessageService(uow=uow1, fanout_service=chat_fanout_stub, fcm_service=chat_fcm_stub)
        ack = await svc1.send_message(
            sender_user_id=user_a,
            sender_session_id="WS_A",
            room_id=room_id,
            client_msg_id=cmid,
            msg_type=MessageType.TEXT,
            content="첫 메시지",
        )
        assert ack.server_seq > 0

        # dedupe 키가 실 Redis 에 남아있어야 함
        key = dedupe_key(user_a, cmid)
        assert await redis_dedupe.exists(key) == 1, (
            f"정상 송신 후 dedupe 키 {key} 가 사라짐 — 같은 cmid 재전송이 중복 메시지를 만들 수 있음"
        )

        # 같은 cmid 재전송은 ValueError ("이미 처리된 메시지")
        uow2 = UnitOfWork(session=session_factory)
        svc2 = MessageService(uow=uow2, fanout_service=chat_fanout_stub, fcm_service=chat_fcm_stub)
        with pytest.raises(ValueError, match="이미 처리된"):
            await svc2.send_message(
                sender_user_id=user_a,
                sender_session_id="WS_A",
                room_id=room_id,
                client_msg_id=cmid,
                msg_type=MessageType.TEXT,
                content="중복 시도",
            )
