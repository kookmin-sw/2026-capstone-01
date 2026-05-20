"""Redis 명령 / Lua script 호출 instrumentation.

모듈명을 `redis_client` 로 둔 이유 — 패키지 내부에서 `redis` 로 두면 외부 `redis` 패키지와
헷갈리기 쉬워 명시적 구분.
"""
import time

from app.core.metric import (
    REDIS_COMMAND_DURATION,
    REDIS_COMMAND_ERRORS_TOTAL,
    REDIS_LUA_SCRIPT_RUN_TOTAL,
)


# 실제 호출하는 명령 화이트리스트. 그 외는 'other' 통합.
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
    """Redis 명령 이름을 enum 라벨로 정규화. `SCRIPT LOAD` 같은 두 단어 명령은 첫 단어만."""
    if isinstance(cmd, bytes):
        cmd = cmd.decode("ascii", errors="replace")
    if not isinstance(cmd, str):
        return "other"
    upper = cmd.upper().split(maxsplit=1)[0] if cmd else ""
    return upper if upper in _KNOWN_REDIS_COMMANDS else "other"


def instrument_redis_client(client, db: str) -> None:
    """redis.asyncio.Redis 의 `execute_command` 를 monkey-patch 해 단일 명령 측정.

    `redis.from_url()` 직후 1회. pipeline 은 `send_packed_command` 경로라 우회.
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
    """AsyncScript 호출에 run_total 카운트 부착. SHA / EVALSHA fallback 동작은 그대로 위임."""

    def __init__(self, script, name: str) -> None:
        self._script = script
        self._name = name


    async def __call__(self, *args, **kwargs):
        REDIS_LUA_SCRIPT_RUN_TOTAL.labels(script=self._name).inc()
        return await self._script(*args, **kwargs)


    def __getattr__(self, item):
        return getattr(self._script, item)


def instrument_lua_script(script, name: str):
    """AsyncScript 를 `_InstrumentedScript` 로 감싼다. `LuaScripts.load()` 에서 호출."""
    return _InstrumentedScript(script, name)
