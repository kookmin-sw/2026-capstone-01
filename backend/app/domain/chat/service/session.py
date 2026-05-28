"""WS 세션의 Redis 상태 관리.

키:
- `sess:{session_id}`     HASH    user_id, node_id, token_jti, connected_at (TTL 90s)
- `sessions:{user_id}`    ZSET    score=만료시각ms, member=session_id
- `ws_route:{session_id}` STRING  node_id (TTL 90s, fan_out_to_session 라우팅용)

ZSET 의 score 가 만료시각이라 `ZREMRANGEBYSCORE -inf <now>` 한 번으로 죽은 세션 청소 — 자가 치유.
"""
import time

from app.util.id_generator import generate_session_id
from app.domain.chat.service.fanout import FanoutService
from app.core.redis import get_redis_client
from app.core.logger import get_logger
from app.core.chat.redis_key import (
    sess_key,
    sessions_key,
    ws_route_key,
    SESSION_TTL,
    MAX_SESSIONS_PER_USER,
)
from app.config.setting import settings


logger = get_logger("chat.session")


class SessionService:
    """WS 세션 생명주기 — 생성 / heartbeat / 종료 / 한도 초과 revoke."""

    def __init__(self, fanout_service: FanoutService):
        self._fanout = fanout_service


    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)


    @classmethod
    def _expires_ms(cls, now_ms: int | None = None) -> int:
        if now_ms is None:
            now_ms = cls._now_ms()
        return now_ms + SESSION_TTL * 1000


    async def create_session(self, user_id: str, token_jti: str) -> str:
        """WS 연결 시 호출 — 새 session_id 발급 후 Redis 3키 + 한도 체크."""
        session_id = generate_session_id()
        now_ms = self._now_ms()
        expires_ms = now_ms + SESSION_TTL * 1000

        redis = await get_redis_client()
        pipe = redis.pipeline(transaction=True)
        pipe.hset(sess_key(session_id), mapping={
            "user_id": user_id,
            "node_id": settings.NODE_ID,
            "token_jti": token_jti,
            "connected_at": str(now_ms),
        })
        pipe.expire(sess_key(session_id), SESSION_TTL)
        pipe.zadd(sessions_key(user_id), {session_id: expires_ms})
        pipe.set(ws_route_key(session_id), settings.NODE_ID, ex=SESSION_TTL)
        await pipe.execute()

        await self._enforce_session_limit(user_id)
        return session_id


    async def heartbeat(self, session_id: str, user_id: str) -> None:
        """ping/pong 시 세 키 TTL 을 pipeline 1번으로 원자 연장.

        `ZADD XX` — 이미 있는 멤버의 score 만 갱신. 죽은 세션 부활 방지.
        """
        new_expires_ms = self._expires_ms()
        redis = await get_redis_client()
        pipe = redis.pipeline(transaction=True)
        pipe.expire(sess_key(session_id), SESSION_TTL)
        pipe.expire(ws_route_key(session_id), SESSION_TTL)
        pipe.zadd(sessions_key(user_id), {session_id: new_expires_ms}, xx=True)
        await pipe.execute()


    async def update_token_jti(self, session_id: str, new_token_jti: str) -> None:
        """JWT refresh 시 token_jti 만 갱신. session_id 는 유지."""
        redis = await get_redis_client()
        await redis.hset(sess_key(session_id), "token_jti", new_token_jti)


    async def session_exists(self, session_id: str) -> bool:
        """매 op 진입부에서 호출 — False 면 revoke 된 상태 (TTL/DEL/강제 로그아웃 동일)."""
        redis = await get_redis_client()
        return bool(await redis.exists(sess_key(session_id)))


    async def get_user_id(self, session_id: str) -> str | None:
        """세션의 소유 user_id (없으면 None)."""
        redis = await get_redis_client()
        value = await redis.hget(sess_key(session_id), "user_id")
        return value if value else None


    async def terminate_session(self, session_id: str, user_id: str) -> None:
        """WS 종료 / 명시 로그아웃 시 Redis 상태 정리.

        호출 순서: FanoutService.unregister_ws → 본 메서드 → WS close.
        """
        redis = await get_redis_client()
        pipe = redis.pipeline(transaction=True)
        pipe.delete(sess_key(session_id))
        pipe.delete(ws_route_key(session_id))
        pipe.zrem(sessions_key(user_id), session_id)
        await pipe.execute()


    async def revoke_all_sessions(self, user_id: str) -> int:
        """유저의 모든 활성 세션 강제 종료 — 회원 탈퇴 등 외부 정책에서 호출.

        TTL 만료를 기다리지 않고 즉시 정리해 송수신 윈도우를 닫는다.
        오프라인 유저는 0 반환.
        """
        redis = await get_redis_client()
        session_ids = await redis.zrange(sessions_key(user_id), 0, -1)
        if not session_ids:
            return 0

        for sid in session_ids:
            await self._fanout.fan_out_to_session(
                sid, {"type": "session_revoked", "session_id": sid},
            )

        pipe = redis.pipeline(transaction=True)
        for sid in session_ids:
            pipe.delete(sess_key(sid), ws_route_key(sid))
        pipe.delete(sessions_key(user_id))
        await pipe.execute()

        logger.info(
            "전체 세션 revoke (회원 탈퇴 등): user_id={}, revoked_count={}",
            user_id, len(session_ids),
        )
        return len(session_ids)


    async def _enforce_session_limit(self, user_id: str) -> None:
        """ZCARD > MAX 면 가장 오래된 세션부터 revoke. 만료분은 ZREMRANGEBYSCORE 로 선청소."""
        redis = await get_redis_client()

        now_ms = self._now_ms()
        await redis.zremrangebyscore(sessions_key(user_id), "-inf", now_ms)

        count = await redis.zcard(sessions_key(user_id))
        while count > MAX_SESSIONS_PER_USER:
            oldest = await redis.zrange(sessions_key(user_id), 0, 0)
            if not oldest:
                break
            old_sid = oldest[0]

            await self._fanout.fan_out_to_session(
                old_sid,
                {"type": "session_revoked", "session_id": old_sid},
            )

            pipe = redis.pipeline(transaction=True)
            pipe.zrem(sessions_key(user_id), old_sid)
            pipe.delete(sess_key(old_sid), ws_route_key(old_sid))
            await pipe.execute()

            logger.info(
                "세션 한도 초과로 revoke: user_id={}, revoked_session_id={}",
                user_id, old_sid,
            )
            count -= 1
