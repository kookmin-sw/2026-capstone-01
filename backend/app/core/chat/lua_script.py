"""Lua 스크립트 로더 / 레지스트리.

startup 시 1회 `.lua` 파일을 읽어 redis-py 의 `register_script()` 로 래핑.
`AsyncScript` 가 EVALSHA 우선 / NOSCRIPT 시 EVAL fallback 까지 자동 처리하므로
SHA 캐싱은 우리가 손대지 않는다.
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
    """로드된 스크립트 보관. `load()` 호출 후 사용 가능."""

    def __init__(self) -> None:
        self.incr_fast: Optional[AsyncScript] = None
        self.recover_and_incr: Optional[AsyncScript] = None
        self.force_jump: Optional[AsyncScript] = None
        self.incr_with_ttl: Optional[AsyncScript] = None


    def load(self, hot_client: Redis) -> None:
        """startup 1회. `instrument_lua_script` 로 감싸 호출 카운트 자동 부착."""
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
