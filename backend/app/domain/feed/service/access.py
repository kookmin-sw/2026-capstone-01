"""피드 게시물 접근 권한 — service 간 공유 helper.

`FeedPostService` (목록 조회) / `FeedPostLikeService` (좋아요) / `FeedPostCommentService`
(댓글) 가 모두 동일한 "viewer 가 owner 의 피드 / 단건 게시물을 볼 수 있는가" 검증을 공유한다.
service-to-service 의존을 만들지 않기 위해 free function 으로 노출하고 session 을 명시적으로
받는다.

규칙:
    - block 우선: 양방향 차단 어느 쪽이든 → `FeedBlockedError` (403)
    - friendship: status == ACCEPTED 만 친구로 인정 (PENDING / REJECTED 는 비친구)
    - visibility 미충족: `FeedNotFoundError` (404 — "존재하지 않는 글" 로 일원화해 정보 누출 회피)

규칙 자체는 `visibility.py::can_view` 가 단일 진입점. 본 모듈은 (DB 조회 + can_view 호출)
의 합성만 책임진다.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.feed.service.visibility import can_view
from app.domain.feed.service.exception import FeedBlockedError, FeedNotFoundError
from app.domain.feed.repository.feed_post import FeedPostRepository
from app.domain.feed.model.feed_post import FeedPost, FeedVisibility
from app.domain.friend.repository.friendship import FriendshipRepository
from app.domain.friend.repository.user_block import UserBlockRepository
from app.domain.friend.model.friendship import FriendshipStatus


async def resolve_viewer_visibilities(
    session: AsyncSession,
    *,
    viewer_id: str,
    owner_id: str,
) -> list[FeedVisibility]:
    """viewer 가 owner 피드에서 볼 수 있는 visibility 부분집합.

    본인 fast-path: 차단/친구 조회 없이 모든 visibility (DB hit 2 절약).

    raises:
        FeedBlockedError: 양방향 차단 — viewer 의 피드 접근 자체 차단.
    """
    if viewer_id == owner_id:
        return list(FeedVisibility)

    block_repo = UserBlockRepository(session)
    friend_repo = FriendshipRepository(session)

    blocks = await block_repo.find_blocks_between(viewer_id, owner_id)
    if blocks:
        raise FeedBlockedError("차단 관계인 유저의 피드에 접근할 수 없습니다.")

    friendship = await friend_repo.find_between(viewer_id, owner_id)
    is_friend = (
        friendship is not None and friendship.status == FriendshipStatus.ACCEPTED
    )

    return [
        v for v in FeedVisibility
        if can_view(
            viewer_id=viewer_id,
            owner_id=owner_id,
            image_visibility=v,
            is_friend=is_friend,
            is_blocked_either_way=False,  # 위에서 이미 거절됨
        )
    ]


async def load_viewable_post(
    session: AsyncSession,
    *,
    viewer_id: str,
    post_id: str,
) -> FeedPost:
    """post 단건 로드 + viewer 가 볼 수 있는지 검증.

    `좋아요 추가`, `댓글 작성`, `댓글 목록 조회` 등의 진입점이 공통으로 호출 — 게시물
    가시성을 transitively 적용한다. 보이지 않는 글에 대한 좋아요/댓글 시도는 거절.

    응답 매핑 정책:
        - 미존재          → FeedNotFoundError (404)
        - 양방향 차단      → FeedBlockedError (403)
        - visibility 미충족 → FeedNotFoundError (404 — "존재하지 않는 글" 일원화)

    "visibility 미충족 → 404" 는 의도적 — 403 으로 응답하면 "그런 글이 있긴 하다" 가 누출되어
    PRIVATE / FRIENDS-only 게시물 존재 여부 정보가 빠진다. 404 로 일원화해 enumeration 차단.

    raises:
        FeedNotFoundError, FeedBlockedError
    """
    repo = FeedPostRepository(session)
    # access check 경로는 .post 만 unwrap 하므로 is_liked 자체는 안 쓰지만, 단일 진입점 유지를
    # 위해 viewer_id 를 그대로 전달 (subquery 비용 ~0.3ms 무시).
    row = await repo.find_by_post_id(post_id, viewer_id=viewer_id)
    if row is None:
        raise FeedNotFoundError("존재하지 않는 게시물입니다.")

    # 좋아요/댓글 access 검증은 카운트 무관 — `.post` 만 unwrap (메서드 분화 회피로 카운트
    # subquery 오버헤드 ~0.5ms 감수).
    post = row.post

    # 본인 fast-path — 모든 visibility 접근 가능 (차단/친구 조회 skip).
    if post.user_id == viewer_id:
        return post

    visibilities = await resolve_viewer_visibilities(
        session, viewer_id=viewer_id, owner_id=post.user_id,
    )
    if post.visibility not in visibilities:
        raise FeedNotFoundError("존재하지 않는 게시물입니다.")
    return post
