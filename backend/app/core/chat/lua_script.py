"""Lua 스크립트 로더 및 레지스트리.

- 앱 startup 시 1회 `.lua` 파일을 읽어 redis-py 의 `register_script()` 로 래핑.
- `register_script()` 는 EVALSHA 우선 / NOSCRIPT 시 EVAL 자동 fallback — SHA 캐싱 로직을 우리가 짤 필요 없음
- hot 클라이언트에 바인딩하고, dedupe 호출 시엔 `client=` 인자로 override.
"""
from typing import Optional
from redis.commands.core import AsyncScript
from redis.asyncio import Redis
from pathlib import Path

from app.core.instrumentation import instrument_lua_script


_LUA_DIR = Path(__file__).parent / "lua"


def _read(name: str) -> str:
    return (_LUA_DIR / name).read_text(encoding="utf-8")


class LuaScripts:
    """로드된 4종 스크립트 객체 보관. `load()` 호출 후 사용 가능."""

    def __init__(self) -> None:
        self.incr_fast: Optional[AsyncScript] = None
        self.recover_and_incr: Optional[AsyncScript] = None
        self.force_jump: Optional[AsyncScript] = None
        self.incr_with_ttl: Optional[AsyncScript] = None


    def load(self, hot_client: Redis) -> None:
        """startup 에서 1회 호출. 파일 I/O 동기로 끝내고 Script 객체만 보유.

        instrument_lua_script wrapper 로 감싸 호출 시 redis_lua_script_run_total 자동 카운트.
        AsyncScript 의 EVALSHA / EVAL fallback 동작은 그대로 위임.
        """
        self.incr_fast = instrument_lua_script(
            hot_client.register_script(_read("incr_fast.lua")), "incr_fast",
        )
        self.recover_and_incr = instrument_lua_script(
            hot_client.register_script(_read("recover_and_incr.lua")), "recover_and_incr",
        )
        self.force_jump = instrument_lua_script(
            hot_client.register_script(_read("force_jump.lua")), "force_jump",
        )
        self.incr_with_ttl = instrument_lua_script(
            hot_client.register_script(_read("incr_with_ttl.lua")), "incr_with_ttl",
        )


lua_scripts = LuaScripts()
