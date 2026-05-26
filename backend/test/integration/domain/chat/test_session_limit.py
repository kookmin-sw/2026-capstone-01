"""PHASE_1 통합 체크리스트 — "동일 유저 11 번째 로그인 → 가장 오래된 세션 revoke".

단위 테스트가 Redis mock 기반으로 이미 존재하지만, ZREMRANGEBYSCORE + ZRANGE + 삭제
pipeline 이 실 Redis ZSET 에서 정확히 동작하는지는 통합에서 증명해야 한다.
"""
import pytest
import asyncio

from app.core.chat.redis_key import (
    MAX_SESSIONS_PER_USER,
    sess_key,
    sessions_key,
    ws_route_key,
)


pytestmark = pytest.mark.integration


class TestSessionLimitOnRealRedis:
    async def test_exceeding_limit_revokes_oldest_session(
        self, session_service, redis_hot, chat_fanout_stub,
    ):
        user_id = "USER_LIMIT"
        sids: list[str] = []

        # MAX+1 번 create_session. sleep 은 ZSET score (만료시각 ms) 를 강제로
        # 서로 다르게 만들기 위함 — 같은 ms 에 몰리면 "가장 오래된" 이 member 문자열
        # 순으로 결정되어 테스트 의도와 엇갈릴 수 있다.
        for i in range(MAX_SESSIONS_PER_USER + 1):
            sid = await session_service.create_session(user_id, f"jti-{i}")
            sids.append(sid)
            await asyncio.sleep(0.003)

        # 방금 만든 세션 포함 ZCARD 는 MAX 로 수렴 (1 개 revoke 됨)
        assert await redis_hot.zcard(sessions_key(user_id)) == MAX_SESSIONS_PER_USER

        oldest_sid = sids[0]

        # oldest 의 세 키가 모두 삭제됐는지 — sess / ws_route / sessions ZSET 엔트리
        assert await redis_hot.exists(sess_key(oldest_sid)) == 0
        assert await redis_hot.exists(ws_route_key(oldest_sid)) == 0
        assert await redis_hot.zscore(sessions_key(user_id), oldest_sid) is None

        # fan_out_to_session 으로 session_revoked 발행 1회
        revoked_calls = [
            call for call in chat_fanout_stub.fan_out_to_session.await_args_list
            if call.args[0] == oldest_sid
        ]
        assert len(revoked_calls) == 1
        assert revoked_calls[0].args[1] == {
            "type": "session_revoked",
            "session_id": oldest_sid,
        }

        # 나머지 10 개 세션은 모두 살아있고 ZSET 에도 존재
        for sid in sids[1:]:
            assert await redis_hot.exists(sess_key(sid)) == 1
            assert await redis_hot.exists(ws_route_key(sid)) == 1
            assert await redis_hot.zscore(sessions_key(user_id), sid) is not None


    async def test_under_limit_does_not_revoke(
        self, session_service, redis_hot, chat_fanout_stub,
    ):
        """MAX 번 로그인까지는 revoke 발생 없음."""
        user_id = "USER_UNDER"
        for i in range(MAX_SESSIONS_PER_USER):
            await session_service.create_session(user_id, f"jti-{i}")
            await asyncio.sleep(0.003)

        assert await redis_hot.zcard(sessions_key(user_id)) == MAX_SESSIONS_PER_USER
        chat_fanout_stub.fan_out_to_session.assert_not_awaited()
