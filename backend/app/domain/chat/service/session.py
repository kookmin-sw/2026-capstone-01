"""WS 세션의 Redis 상태 관리.

관리 대상 키:
    - sess:{session_id}       HASH  : user_id, node_id, token_jti, connected_at (TTL 90s)
    - sessions:{user_id}      ZSET  : score=만료시각(ms), member=session_id
    - ws_route:{session_id}   STRING: node_id (TTL 90s, Phase 4 fan_out_to_session 에서 사용)

세션 ZSET 은 만료시각을 score 로 박아두기 때문에 `ZREMRANGEBYSCORE -inf <now>` 한 번으로
죽은 세션을 원자 청소할 수 있다. 따로 refcount / heartbeat 이벤트 불필요 — 자가 치유.
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
    """WS 세션 생명주기 관리 — 생성 / heartbeat / 종료 / 한도 초과 revoke.

    Container 에서 Singleton 으로 등록되며 `FanoutService` 와만 협력한다. Redis 클라이언트는
    매 메서드에서 `await get_redis_client()` 로 가져온다 — 실제 커넥션은 Step 3 의 cached
    singleton 이라 왕복 비용 없음.
    """

    def __init__(self, fanout_service: FanoutService):
        self._fanout = fanout_service


    # ──────────────────── 유틸 ────────────────────

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)


    @classmethod
    def _expires_ms(cls, now_ms: int | None = None) -> int:
        if now_ms is None:
            now_ms = cls._now_ms()
        return now_ms + SESSION_TTL * 1000


    # ──────────────────── 생성 ────────────────────

    async def create_session(self, user_id: str, token_jti: str) -> str:
        """WS 연결 시 호출. 새 session_id 발급 후 Redis 3키 + 한도 체크.

        returns: 발급된 `session_id`
        """
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

        # 한도 체크 (방금 만든 세션 포함 ZCARD 기준) — 초과 시 가장 오래된 것부터 revoke
        await self._enforce_session_limit(user_id)

        return session_id


    # ──────────────────── heartbeat / refresh ────────────────────

    async def heartbeat(self, session_id: str, user_id: str) -> None:
        """ping/pong 시 세 키 TTL 을 pipeline 한 번으로 원자 연장.

        `ZADD XX` 로 이미 있는 멤버의 score 만 갱신 — 죽은 세션이 heartbeat 으로 부활하는
        일을 방지.
        """
        new_expires_ms = self._expires_ms()
        redis = await get_redis_client()
        pipe = redis.pipeline(transaction=True)
        pipe.expire(sess_key(session_id), SESSION_TTL)
        pipe.expire(ws_route_key(session_id), SESSION_TTL)
        pipe.zadd(sessions_key(user_id), {session_id: new_expires_ms}, xx=True)
        await pipe.execute()


    async def update_token_jti(self, session_id: str, new_token_jti: str) -> None:
        """JWT refresh 성공 시 token_jti 갱신. session_id 는 변경하지 않는다 (P6)."""
        redis = await get_redis_client()
        await redis.hset(sess_key(session_id), "token_jti", new_token_jti)


    # ──────────────────── 조회 ────────────────────

    async def session_exists(self, session_id: str) -> bool:
        """매 op 처리 진입부에서 호출. False 면 revoke 된 상태이므로 close(4001) 유도.

        TTL 만료 / 명시 DEL / 강제 로그아웃 모두 여기서 동일하게 False.
        """
        redis = await get_redis_client()
        return bool(await redis.exists(sess_key(session_id)))


    async def get_user_id(self, session_id: str) -> str | None:
        """세션의 소유 user_id 를 반환 (존재하지 않으면 None)."""
        redis = await get_redis_client()
        value = await redis.hget(sess_key(session_id), "user_id")
        return value if value else None


    # ──────────────────── 종료 ────────────────────

    async def terminate_session(self, session_id: str, user_id: str) -> None:
        """WS 종료 / 명시 로그아웃 시 Redis 상태 전부 정리.

        호출 순서 주의: FanoutService.unregister_ws 로 **로컬 dict 먼저**
        제거 → Redis 정리 → WS close. 이 함수는 Redis 정리만 책임.
        """
        redis = await get_redis_client()
        pipe = redis.pipeline(transaction=True)
        pipe.delete(sess_key(session_id))
        pipe.delete(ws_route_key(session_id))
        pipe.zrem(sessions_key(user_id), session_id)
        await pipe.execute()


    async def revoke_all_sessions(self, user_id: str) -> int:
        """유저의 모든 활성 세션 강제 종료 — 회원 탈퇴 등 외부 정책 호출용.

        `_enforce_session_limit` 의 한도 초과 revoke 와 동일 절차이며 전수 종료라는 점만
        다르다. 각 세션에 `session_revoked` 직송 → Redis 키 3종 정리. `sessions:{uid}`
        ZSET 은 비어지므로 통째로 DEL 해 잔여 빈 키 누수 방지.

        TTL(90s) 만료를 기다리지 않고 즉시 정리해 INACTIVE 전환 직후 송수신 윈도우를 닫는다.

        Returns:
            revoke 처리된 세션 수 (오프라인 유저 0).
        """
        redis = await get_redis_client()
        session_ids = await redis.zrange(sessions_key(user_id), 0, -1)
        if not session_ids:
            return 0

        # session_revoked 이벤트 — node_channel 모드에선 ws_route 로 타깃 노드 라우팅.
        # WS 핸들러는 수신 시 자가 close 처리.
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


    # ──────────────────── 내부 — 한도 초과 처리 ────────────────────

    async def _enforce_session_limit(self, user_id: str) -> None:
        """`sessions:{user_id}` ZCARD > MAX 이면 가장 오래된 세션부터 revoke.

        1) 만료분 원자 청소 (`ZREMRANGEBYSCORE -inf now_ms`) — 자가 치유
        2) 초과분 만큼 `ZRANGE 0 0` 반복해 가장 오래된 세션 revoke
           - `fan_out_to_session` 으로 `session_revoked` 이벤트 직송
           - Redis 상태(`sess` / `ws_route` / `sessions`) 정리
        """
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
