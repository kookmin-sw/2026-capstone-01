"""피드 접근 권한 — service 간 공유 helper.

FeedPostService / FeedPostLikeService / FeedPostCommentService 가 공유하는 "viewer 가
owner 피드를 볼 수 있는가" 검증. service-to-service 의존을 피하려 free function + 명시 session.

block 우선 → friendship (ACCEPTED 만) → visibility 미충족은 404 일원화 (정보 누출 회피).
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.friend.repository.user_block import UserBlockRepository
from app.domain.friend.repository.friendship import FriendshipRepository
from app.domain.friend.model.friendship import FriendshipStatus
from app.domain.feed.service.visibility import can_view
from app.domain.feed.service.exception import FeedBlockedError, FeedNotFoundError
from app.domain.feed.repository.feed_post import FeedPostRepository
from app.domain.feed.model.feed_post import FeedPost, FeedVisibility


async def resolve_viewer_visibilities(
    session: AsyncSession,
    *,
    viewer_id: str,
    owner_id: str,
) -> list[FeedVisibility]:
    """viewer 가 owner 피드에서 볼 수 있는 visibility 부분집합.

    본인 fast-path: 차단/친구 조회 skip.

    raises:
        FeedBlockedError: 양방향 차단.
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
            is_blocked_either_way=False,
        )
    ]


async def load_viewable_post(
    session: AsyncSession,
    *,
    viewer_id: str,
    post_id: str,
) -> FeedPost:
    """단건 로드 + viewer 의 가시성 검증.

    매핑: 미존재 → 404, 양방향 차단 → 403, visibility 미충족 → 404 (enumeration 차단).
    """
    repo = FeedPostRepository(session)
    # access check 만 필요해도 viewer_id 전달 — 단일 진입점 유지 (subquery 비용 ~0.3ms 무시).
    row = await repo.find_by_post_id(post_id, viewer_id=viewer_id)
    if row is None:
        raise FeedNotFoundError("존재하지 않는 게시물입니다.")

    post = row.post

    if post.user_id == viewer_id:
        return post

    visibilities = await resolve_viewer_visibilities(
        session, viewer_id=viewer_id, owner_id=post.user_id,
    )
    if post.visibility not in visibilities:
        raise FeedNotFoundError("존재하지 않는 게시물입니다.")
    return post
