"""Redis 명령 / Lua script 호출 instrumentation.

파일명을 `redis_client` 로 둔 이유: 패키지 내부에서 `redis` 로 두면 `import redis` 가
상대 import 처럼 해석되거나 IDE 가 헷갈리기 쉬워 외부 `redis` 패키지와 명시적으로 구분.
"""
import time

from app.core.metric import (
    REDIS_COMMAND_DURATION,
    REDIS_COMMAND_ERRORS_TOTAL,
    REDIS_LUA_SCRIPT_RUN_TOTAL,
)


# 우리 코드가 실제 호출하는 명령 화이트리스트. 그 외는 'other' 로 통합 — 카디널리티 통제.
_KNOWN_REDIS_COMMANDS = frozenset({
    "GET", "SET", "DEL", "EXISTS", "EXPIRE", "TTL", "PERSIST", "MGET", "MSET",
    "INCR", "DECR", "INCRBY", "DECRBY",
    "HGET", "HSET", "HMSET", "HMGET", "HGETALL", "HDEL", "HKEYS",
    "HEXISTS", "HLEN", "HINCRBY",
    "SADD", "SPOP", "SCARD", "SMEMBERS", "SREM", "SISMEMBER",
    "ZADD", "ZRANGE", "ZRANGEBYSCORE", "ZREMRANGEBYSCORE",
    "ZSCORE", "ZREM", "ZCARD",
    "PUBLISH", "SUBSCRIBE", "UNSUBSCRIBE", "PSUBSCRIBE",
    "EVAL", "EVALSHA", "SCRIPT",
    "PING", "INFO", "DBSIZE", "FLUSHDB",
    "MULTI", "EXEC", "DISCARD", "WATCH", "UNWATCH",
})


def _normalize_redis_command(cmd) -> str:
    """Redis command 이름을 enum 라벨로 정규화. bytes / str 모두 처리.

    SCRIPT LOAD 같이 두 단어 명령은 첫 단어만 사용 (SCRIPT). 화이트리스트 외는 'other'.
    """
    if isinstance(cmd, bytes):
        cmd = cmd.decode("ascii", errors="replace")
    if not isinstance(cmd, str):
        return "other"
    upper = cmd.upper().split(maxsplit=1)[0] if cmd else ""
    return upper if upper in _KNOWN_REDIS_COMMANDS else "other"


def instrument_redis_client(client, db: str) -> None:
    """redis.asyncio.Redis 인스턴스의 execute_command 를 instrumented 버전으로 monkey-patch.

    redis.from_url() 직후 1 회 호출. 단일 명령만 잡힌다 — pipeline 은 send_packed_command
    경로라 우회. 운영 가시성에 충분.
    """
    if getattr(client, "_krip_instrumented", False):
        return

    original = client.execute_command

    async def instrumented(*args, **options):
        if not args:
            return await original(*args, **options)
        cmd_label = _normalize_redis_command(args[0])
        started = time.perf_counter()
        try:
            return await original(*args, **options)
        except Exception as exc:
            REDIS_COMMAND_ERRORS_TOTAL.labels(
                command=cmd_label, db=db, exc_type=type(exc).__name__,
            ).inc()
            raise
        finally:
            elapsed = time.perf_counter() - started
            REDIS_COMMAND_DURATION.labels(command=cmd_label, db=db).observe(elapsed)

    client.execute_command = instrumented
    client._krip_instrumented = True


class _InstrumentedScript:
    """AsyncScript 호출에 redis_lua_script_run_total 카운트 부착.

    내부 script 의 SHA, EVALSHA fallback, NOSCRIPT 재로드 등 동작은 그대로 위임된다.
    """

    def __init__(self, script, name: str) -> None:
        self._script = script
        self._name = name

    async def __call__(self, *args, **kwargs):
        REDIS_LUA_SCRIPT_RUN_TOTAL.labels(script=self._name).inc()
        return await self._script(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._script, item)


def instrument_lua_script(script, name: str):
    """AsyncScript 를 _InstrumentedScript wrapper 로 감싼다.

    LuaScripts.load() 안에서 register_script 결과에 부착.
    """
    return _InstrumentedScript(script, name)
