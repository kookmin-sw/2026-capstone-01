"""Redis 명령 / Lua script 실행 메트릭.

command enum 은 우리가 실제 호출하는 명령만 화이트리스트 (instrumentation/redis_client 참조),
나머지는 'other' 로 통합.
파일명 `redis_client` 는 외부 `redis` 패키지와의 import 혼동 회피.
"""
from prometheus_client import Counter, Histogram


REDIS_COMMAND_DURATION = Histogram(
    "redis_command_duration_seconds",
    "Redis single command execution duration. Pipeline 은 execute_command 우회하므로 미포함.",
    labelnames=("command", "db"),
    buckets=(0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.5, 1.0),
)

REDIS_COMMAND_ERRORS_TOTAL = Counter(
    "redis_command_errors_total",
    "Redis command exceptions grouped by command, db, and exception class name.",
    labelnames=("command", "db", "exc_type"),
)

REDIS_LUA_SCRIPT_RUN_TOTAL = Counter(
    "redis_lua_script_run_total",
    "Lua script invocation count.",
    labelnames=("script",),
)
