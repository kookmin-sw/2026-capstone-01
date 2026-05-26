"""Feed 도메인 커스텀 예외 — Router 가 HTTP status 로 매핑.

ValueError                   → 400
PermissionError              → 403 (본인 게시물 아님)
FeedBlockedError             → 403 (PermissionError 하위 — 차단 관계 명시 분리)
FeedNotFoundError            → 404 (미존재 또는 visibility 미충족)
FeedPostCommentNotFoundError → 404
PopupTargetNotFoundError     → 404
"""


class FeedNotFoundError(ValueError):
    """존재하지 않는 게시물. visibility 미충족도 본 예외로 일원화 (정보 누출 회피)."""


class FeedBlockedError(PermissionError):
    """양방향 차단. PermissionError 하위라 기존 `except PermissionError` 가 그대로 catch."""


class FeedPostCommentNotFoundError(ValueError):
    """존재하지 않는 댓글 또는 post_id mismatch (enumeration 차단)."""


class PopupTargetNotFoundError(ValueError):
    """popup 대상 user 미존재 / 회원가입 미완료 일원화 (enumeration 차단)."""
