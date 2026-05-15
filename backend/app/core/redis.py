import redis.asyncio as redis

from app.config.setting import settings
from app.core.instrumentation import instrument_redis_client


# socket-level timeout 정책 — Redis hang 시 코루틴이 영구 stuck 되는 것을 차단.
#
# 기본값 (socket_timeout=None) 은 무한 대기라, Redis 가 SAVE/BGSAVE fork 지연 / AOF
# rewrite 포화 / 네트워크 partition 등으로 응답을 멈추면 호출 코루틴이 영원히 await
# 상태로 머문다. instrumentation 의 try/finally 조차 도달 못 해 메트릭도 침묵.
# request slot 까지 영구 점유되면 uvicorn 워커 동시 처리 한도가 차서 새 요청 거부.
#
# Redis 정상 명령은 ms 단위 (LAN P99 < 5ms, cloud P99 < 20ms) 라 5s 면 정상 트래픽
# jitter 영향 없이 hang 만 잡아낸다. Lua script 도 Redis 의 lua-time-limit=5000ms 가
# 강제 상한이라 충돌 없음.
#
# PubSub 안전성: fanout_dispatcher 의 `pubsub.get_message(timeout=1.0)` 는 application
# 레벨에서 1s polling timeout 을 명시하므로 socket_timeout (5s) 보다 항상 짧다.
# polling 이 먼저 None 반환 후 재진입 → socket 레벨 timeout 은 fire 되지 않음.
#
# 주의: BLPOP / BRPOP / XREAD 같은 blocking 명령을 추가하면 socket_timeout 보다 짧은
# block timeout 을 명시하거나 별도 client (`socket_timeout=None`) 를 따로 만들어야 함.
_REDIS_SOCKET_TIMEOUT_SEC = 5.0
_REDIS_SOCKET_CONNECT_TIMEOUT_SEC = 3.0


class RedisClient:
    """Redis 클라이언트 관리 클래스.

    - hot (DB 0) : 세션/시퀀스/unread/rate 등 핫 데이터
    - dedupe (DB 1) : dedupe 키 전용 격리 — 운영자의 `KEYS dedupe:*` 실수가
      세션/시퀀스에 영향주지 않도록 DB 번호 분리 (§3.3)
    """

    _client: "redis.Redis | None" = None
    _dedupe_client: "redis.Redis | None" = None

    # 캐시 TTL 상수
    DEFAULT_CACHE_TTL = 86400  # 24 hours in seconds
    SHORT_CACHE_TTL = 3600     # 1 hour in seconds
    MEDIUM_CACHE_TTL = 43200   # 12 hours in seconds

    @classmethod
    async def get_client(cls) -> redis.Redis:
        """hot Redis 클라이언트(DB 0)"""
        if cls._client is None:
            cls._client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                encoding="utf-8",
                socket_timeout=_REDIS_SOCKET_TIMEOUT_SEC,
                socket_connect_timeout=_REDIS_SOCKET_CONNECT_TIMEOUT_SEC,
            )
            instrument_redis_client(cls._client, db="hot")
        return cls._client

    @classmethod
    async def get_dedupe_client(cls) -> redis.Redis:
        """dedupe 전용 Redis 클라이언트(DB 1)"""
        if cls._dedupe_client is None:
            cls._dedupe_client = redis.from_url(
                settings.REDIS_URL_DEDUPE,
                decode_responses=True,
                encoding="utf-8",
                socket_timeout=_REDIS_SOCKET_TIMEOUT_SEC,
                socket_connect_timeout=_REDIS_SOCKET_CONNECT_TIMEOUT_SEC,
            )
            instrument_redis_client(cls._dedupe_client, db="dedupe")
        return cls._dedupe_client

    @classmethod
    async def close(cls):
        """Redis 연결 종료 (양쪽 DB)"""
        if cls._client:
            await cls._client.close()
            cls._client = None
        if cls._dedupe_client:
            await cls._dedupe_client.close()
            cls._dedupe_client = None


async def get_redis_client() -> redis.Redis:
    """hot Redis 클라이언트(DB 0) 반환"""
    return await RedisClient.get_client()


async def get_redis_dedupe_client() -> redis.Redis:
    """dedupe 전용 Redis 클라이언트(DB 1) 반환"""
    return await RedisClient.get_dedupe_client()


async def close_redis():
    """Redis 연결 종료"""
    await RedisClient.close()