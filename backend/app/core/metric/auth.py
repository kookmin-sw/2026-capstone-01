"""Auth 미들웨어 실패 분류 메트릭."""
from prometheus_client import Counter


# 인증 실패 카운터.
# auth 미들웨어 11개 실패 분기에서 kind 라벨을 분류해 .inc() 한다.
AUTH_FAILURES = Counter(
    "auth_failures_total",
    "Authentication failures grouped by failure kind.",
    labelnames=("kind",),
)

AUTH_KINDS = (
    "bearer_header_missing",
    "bearer_format_invalid",
    "bearer_token_invalid",
    "cookie_missing",
    "cookie_no_user_id",
    "cookie_expired",
    "cookie_invalid",
    "register_db_error",
    "register_user_not_found",
    "register_withdrawal_pending",
    "register_incomplete",
    "other",
)
