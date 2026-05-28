"""feed 도메인 단위 테스트 공용 Mock 팩토리.

`@transactional` 의 `async with self.uow as session:` 패턴을 충족하는 FakeUnitOfWork +
FeedPostRepository / ObjectStorage 의 AsyncMock + 도메인 모델의 spec'd MagicMock 을 한 곳
에서 만든다. 테스트 파일이 직접 conftest 에서 helper 를 import 하지 않도록 cross-test
재사용 가능한 helper 는 모두 본 모듈에 모은다.
"""
from unittest.mock import AsyncMock, MagicMock
from typing import Optional
from datetime import datetime, timezone

from app.domain.feed.model.feed_post_like import FeedPostLike
from app.domain.feed.model.feed_post_comment import FeedPostComment
from app.domain.feed.dto.feed_post import FeedPostWithCounts
from app.domain.auth.model.user_travel_style import TravelStyle, UserTravelStyle
from app.domain.auth.model.user_detail_inform import UserDetailInform
from app.domain.auth.model.user import User


class FakeUnitOfWork:
    """`@transactional` 데코레이터의 컨텍스트 매니저 인터페이스 충족."""

    def __init__(self, session):
        self._session = session


    async def __aenter__(self):
        return self._session


    async def __aexit__(self, exc_type, exc, tb):
        return False


def make_mock_session() -> MagicMock:
    session = MagicMock(name="session")
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.get = AsyncMock(return_value=None)
    return session


def make_feed_post_repo_mock() -> AsyncMock:
    """FeedPostRepository 의 모든 public 메서드를 AsyncMock 으로."""
    mock = AsyncMock()
    mock.find_by_post_id.return_value = None
    mock.find_by_owner.return_value = []
    mock.save.side_effect = lambda post: post
    mock.update.side_effect = lambda post: post
    mock.delete.return_value = None
    return mock


def make_object_storage_mock() -> MagicMock:
    storage = MagicMock(name="storage")
    storage.upload_to_key = AsyncMock()
    storage.delete_by_prefix = AsyncMock()
    return storage


def make_friendship_repo_mock() -> AsyncMock:
    """FriendshipRepository — `_resolve_viewer_visibilities` 가 `find_between` 만 사용."""
    mock = AsyncMock()
    mock.find_between.return_value = None  # 기본: 관계 없음
    return mock


def make_user_block_repo_mock() -> AsyncMock:
    """UserBlockRepository — `_resolve_viewer_visibilities` 가 `find_blocks_between` 만 사용."""
    mock = AsyncMock()
    mock.find_blocks_between.return_value = []  # 기본: 차단 없음
    return mock


# ──────────────────── 모델 인스턴스 helper ────────────────────

def make_feed_post_with_counts(
    post,
    *,
    like_count: int = 0,
    comment_count: int = 0,
    is_liked: bool = False,
) -> FeedPostWithCounts:
    """`FeedPostWithCounts(post, like_count, comment_count, is_liked)` 합성 helper.

    repo (`find_by_post_id` / `find_by_owner`) 가 반환하는 row 형태를 테스트에서 합성할 때
    사용. spec=FeedPost 같은 mock post 를 넣고 카운트/좋아요 여부만 지정.
    """
    return FeedPostWithCounts(
        post=post,
        like_count=like_count,
        comment_count=comment_count,
        is_liked=is_liked,
    )


def make_feed_post_like_mock(
    *,
    user_id: str = "USER_a",
    post_id: str = "FDP_x",
    user_name: str = "Alice",
    profile_image_url: Optional[str] = None,
    detail_present: bool = True,
) -> MagicMock:
    """`FeedPostLike` (with joinedload `user.detail`) spec'd MagicMock.

    `find_with_user_by_post` 의 단일 JOIN 결과 한 row 를 시뮬레이션 — service 의
    `_to_liked_user_dto` 가 `like.user.detail` 체이닝을 정확히 매핑하는지 검증할 때 사용.

    `detail_present=False` 로 회원가입 미완료 (detail 결손) 케이스 fallback 도 표현 가능.
    """
    like = MagicMock(spec=FeedPostLike)
    like.user_id = user_id
    like.post_id = post_id
    like.created_at = datetime.now(timezone.utc)

    user = MagicMock(spec=User)
    user.user_id = user_id
    if detail_present:
        detail = MagicMock(spec=UserDetailInform)
        detail.user_id = user_id
        detail.user_name = user_name
        detail.profile_image_url = profile_image_url
        user.detail = detail
    else:
        user.detail = None
    like.user = user
    return like


def make_feed_post_comment_mock(
    *,
    comment_id: str = "FDC_x",
    post_id: str = "FDP_x",
    user_id: str = "USER_author",
    content: str = "hi",
    user_name: str = "Alice",
    profile_image_url: Optional[str] = None,
    detail_present: bool = True,
) -> MagicMock:
    """`FeedPostComment` (with joinedload `user.detail`) spec'd MagicMock.

    `find_by_id` / `find_by_post` 의 단일 JOIN 결과 한 row 시뮬레이션 — service 의
    `_to_dto` 가 `comment.user.detail` 체이닝을 정확히 매핑하는지 검증할 때 사용.
    `make_feed_post_like_mock` 와 동일 패턴 (좋아요/댓글 mock 일관).

    `detail_present=False` 로 회원가입 미완료 (detail 결손) 케이스 fallback 표현 가능.
    """
    c = MagicMock(spec=FeedPostComment)
    c.comment_id = comment_id
    c.post_id = post_id
    c.user_id = user_id
    c.content = content
    c.created_at = c.updated_at = datetime.now(timezone.utc)

    user = MagicMock(spec=User)
    user.user_id = user_id
    if detail_present:
        detail = MagicMock(spec=UserDetailInform)
        detail.user_id = user_id
        detail.user_name = user_name
        detail.profile_image_url = profile_image_url
        user.detail = detail
    else:
        user.detail = None
    c.user = user
    return c


def make_user_with_profile_mock(
    *,
    user_id: str = "USER_owner",
    user_name: str = "조현상",
    nationality: str = "korea",
    travel_styles: Optional[list[TravelStyle]] = None,
    profile_image_url: Optional[str] = "https://x/p.jpg",
    detail_present: bool = True,
) -> MagicMock:
    """`User` + `detail` + `travel_styles` 한 묶음의 spec'd MagicMock.

    `UserRepository.find_by_id_with_profile` 의 단일 SELECT (joinedload detail +
    travel_styles) 결과를 시뮬레이션 — popup service 의 `user.detail.user_name` /
    `[s.style for s in user.travel_styles]` 체이닝 매핑을 검증할 때 사용.

    `detail_present=False` 로 회원가입 미완료 (detail 결손) 케이스 표현 가능.
    `travel_styles=None` (default) → `[ACTIVITY]` 1건 (특별한 의미 없는 baseline).
    """
    user = MagicMock(spec=User)
    user.user_id = user_id

    if detail_present:
        detail = MagicMock(spec=UserDetailInform)
        detail.user_id = user_id
        detail.user_name = user_name
        detail.nationality = nationality
        detail.profile_image_url = profile_image_url
        user.detail = detail
    else:
        user.detail = None

    styles = travel_styles if travel_styles is not None else [TravelStyle.ACTIVITY]
    user.travel_styles = [_mk_travel_style(user_id=user_id, style=s) for s in styles]
    return user


def _mk_travel_style(*, user_id: str, style: TravelStyle) -> MagicMock:
    """internal — `UserTravelStyle` row mock. `make_user_with_profile_mock` 전용."""
    s = MagicMock(spec=UserTravelStyle)
    s.user_id = user_id
    s.style = style
    return s
