"""피드 가시성 결정 — 순수 함수 (DB / 외부 의존 없음).

service 레이어가 (block_repo, friend_repo) 결과를 합성해 호출. 규칙 단일 진입점.

규칙:
    is_blocked  → False
    viewer=owner → True
    PUBLIC      → True
    FRIENDS + is_friend → True
    FRIENDS + 비친구 / PRIVATE → False
"""
from app.domain.feed.model.feed_post import FeedVisibility


def can_view(
    *,
    viewer_id: str,
    owner_id: str,
    image_visibility: FeedVisibility,
    is_friend: bool,
    is_blocked_either_way: bool,
) -> bool:
    """관계 조건으로 viewer 가 image 를 볼 수 있는지 판정. keyword-only 로 swap 버그 차단."""
    if is_blocked_either_way:
        return False
    if viewer_id == owner_id:
        return True
    if image_visibility == FeedVisibility.PUBLIC:
        return True
    if image_visibility == FeedVisibility.FRIENDS and is_friend:
        return True
    return False
