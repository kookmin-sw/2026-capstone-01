"""PHASE_1 통합 체크리스트 — "두 유저가 동시에 메시지 송신 → 모두 단조 seq".

`incr_fast.lua` 의 atomic INCR 가 실 Redis 에서 정말 원자적인지, 동시 송신 N 건의
server_seq 가 유니크하고 1..N 로 채워지는지 검증한다. 단위 테스트는 Lua 를 mock 하기
때문에 이 보장은 통합으로만 증명 가능.
"""
import pytest
import asyncio

from app.domain.chat.service.message import MessageService
from app.domain.chat.model.chat_message import MessageType
from app.database.session import UnitOfWork


pytestmark = pytest.mark.integration


# `UnitOfWork.__aenter__` 가 `self.session` 인스턴스 속성에 세션을 저장하므로
# 동시 gather 로 같은 UoW 를 공유하면 race 가 발생한다 — task 별로 신규 UoW.
# row lock 경합 완화를 위해 concurrent 건수는 10 으로 축소 (atomic 증명은 동일).
_CONCURRENT_COUNT = 10


class TestConcurrentSendProducesMonotonicSeq:
    async def test_concurrent_sends_yield_unique_monotonic_seq(
        self, session_factory, direct_room, chat_fanout_stub, chat_fcm_stub, mongo_db, monkeypatch,
    ):
        monkeypatch.setattr(
            "app.domain.chat.service.message.RATE_LIMIT_THRESHOLD",
            _CONCURRENT_COUNT * 2,
        )

        room_id, user_a, user_b = direct_room

        async def send(i: int):
            uow = UnitOfWork(session=session_factory)
            svc = MessageService(uow=uow, fanout_service=chat_fanout_stub, fcm_service=chat_fcm_stub)
            uid = user_a if i % 2 == 0 else user_b
            return await svc.send_message(
                sender_user_id=uid,
                sender_session_id=f"WS_sender_{uid}",
                room_id=room_id,
                client_msg_id=f"cmid-{i}",
                msg_type=MessageType.TEXT,
                content=f"msg {i}",
            )

        acks = await asyncio.gather(*(send(i) for i in range(_CONCURRENT_COUNT)))
        seqs = [ack.server_seq for ack in acks]

        # PHASE_1 "단조 seq" 의 실제 요구는 **유니크** 이다 — Lua atomic (+ 복구 경로의
        # force_jump) 이 결과적으로 중복 없는 seq 를 N 개 발행해야 한다. 첫 메시지
        # 복구 경로에서 `recover_and_incr(base=mongo_max+1000)` 가 뛰는 건 정상.
        assert len(set(seqs)) == _CONCURRENT_COUNT, (
            f"server_seq 에 중복 발생: {sorted(seqs)}"
        )
        assert all(s > 0 for s in seqs), f"비정상 seq: {sorted(seqs)}"

        # Mongo 에도 같은 개수의 unique (chat_room_id, server_seq) 문서가 저장됐는지
        cursor = mongo_db.chat_message.find({"chat_room_id": room_id})
        docs = [doc async for doc in cursor]
        assert len(docs) == _CONCURRENT_COUNT
        assert len({d["server_seq"] for d in docs}) == _CONCURRENT_COUNT
        assert sorted(d["server_seq"] for d in docs) == sorted(seqs), (
            "ACK 의 seq 집합과 Mongo 저장 seq 집합 불일치"
        )

        assert chat_fanout_stub.fan_out_to_room.await_count == _CONCURRENT_COUNT
