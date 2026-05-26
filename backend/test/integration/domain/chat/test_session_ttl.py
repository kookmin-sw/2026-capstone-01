"""PHASE_1 통합 체크리스트 — "ping/pong 90 초 끊김 → 세션 자동 만료".

SESSION_TTL 을 테스트에서 2 초로 낮춘 뒤, heartbeat 없이 방치하면 sess / ws_route
키가 Redis TTL 에 의해 자동 삭제되어 `session_exists` 가 False 로 전환됨을 확인.

sessions ZSET 은 TTL 이 아닌 ZREMRANGEBYSCORE 자가 치유로 청소되므로, 여기서는
`sess` 키 존재 여부를 권위있는 "세션 살아있음" 판정 지표로 간주한다 (§3.4).
"""
import pytest
import asyncio

from app.core.chat.redis_key import sess_key, sessions_key, ws_route_key


pytestmark = pytest.mark.integration


# 실 TTL(90s) 대신 테스트 단축용 TTL (초). Redis TTL 은 초 단위 정수라 2 초가 최소 실용값.
_SHORT_TTL = 2
# TTL 만료 후 여유분 — CI 환경 변동을 고려해 1 초 마진.
_WAIT = _SHORT_TTL + 1


class TestSessionAutoExpiresOnTtl:
    async def test_sess_and_ws_route_keys_disappear_after_ttl(
        self, session_service, redis_hot, monkeypatch,
    ):
        # session_service 모듈에 바인딩된 SESSION_TTL 을 가로챈다.
        monkeypatch.setattr(
            "app.domain.chat.service.session.SESSION_TTL", _SHORT_TTL,
        )

        user_id = "USER_TTL"
        sid = await session_service.create_session(user_id, "jti-1")

        # 직후: 세 키 모두 존재 + session_exists True
        assert await redis_hot.exists(sess_key(sid)) == 1
        assert await redis_hot.exists(ws_route_key(sid)) == 1
        assert await redis_hot.zscore(sessions_key(user_id), sid) is not None
        assert await session_service.session_exists(sid) is True

        # TTL 경과 대기
        await asyncio.sleep(_WAIT)

        # EXPIRE 로 세팅된 두 키는 자동 삭제, session_exists 도 False
        assert await redis_hot.exists(sess_key(sid)) == 0
        assert await redis_hot.exists(ws_route_key(sid)) == 0
        assert await session_service.session_exists(sid) is False


    async def test_heartbeat_revives_ttl(
        self, session_service, redis_hot, monkeypatch,
    ):
        """heartbeat 호출로 TTL 이 연장되어 만료 타이밍이 뒤로 밀림."""
        monkeypatch.setattr(
            "app.domain.chat.service.session.SESSION_TTL", _SHORT_TTL,
        )

        user_id = "USER_HB"
        sid = await session_service.create_session(user_id, "jti-1")

        # TTL 의 절반 경과 시점에 heartbeat — 키 수명이 다시 _SHORT_TTL 로 리셋
        await asyncio.sleep(_SHORT_TTL / 2)
        await session_service.heartbeat(session_id=sid, user_id=user_id)

        # heartbeat 없었으면 죽었을 시점까지 대기
        await asyncio.sleep(_SHORT_TTL / 2 + 0.2)
        assert await session_service.session_exists(sid) is True
        assert await redis_hot.exists(sess_key(sid)) == 1
