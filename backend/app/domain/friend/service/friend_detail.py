from app.domain.friend.repository.user_block import UserBlockRepository
from app.domain.friend.repository.friendship import FriendshipRepository
from app.domain.friend.dto.friend_detail import FriendDetailData
from app.domain.auth.repository.user import UserRepository
from app.database.session import UnitOfWork, transactional


class UserNotFoundError(ValueError):
    """URL 경로로 지정된 유저가 DB 에 존재하지 않음 — 라우터에서 404 로 매핑."""


class FriendDetailService:
    """상대 유저 기본 프로필 + 내 기준 관계 상태 조회."""

    def __init__(self, uow: UnitOfWork):
        self.uow = uow


    @transactional
    async def get_friend_detail(self, viewer_id: str, peer_id: str) -> FriendDetailData:
        """
        1. 상대 유저 존재 + 2차 회원가입 완료 검증
        2. friendship (방향 무관) 조회
        3. viewer → peer 차단 여부 조회
        4. DTO 조립 — 민감 정보(auth_provider, status, email, phone_number) 제외

        예외:
            UserNotFoundError: 유저가 DB 에 존재하지 않음 → 라우터 404
            ValueError: 유저는 존재하지만 2차 회원가입 미완료 → 라우터 400
        """

        user_repo = UserRepository(self._session)
        friendship_repo = FriendshipRepository(self._session)
        block_repo = UserBlockRepository(self._session)

        peer = await user_repo.find_by_id_with_profile(peer_id)
        if peer is None:
            raise UserNotFoundError("존재하지 않는 유저입니다.")
        if peer.detail is None:
            raise ValueError("2차 회원가입이 완료되지 않은 유저입니다.")

        friendship = await friendship_repo.find_between(viewer_id, peer_id)
        i_blocked = await block_repo.has_blocker_blocked(viewer_id, peer_id)

        if friendship is not None:
            friendship_id = friendship.friendship_id
            friendship_status = friendship.status
            is_requester = friendship.requester_id == viewer_id
        else:
            friendship_id = None
            friendship_status = None
            is_requester = None

        return FriendDetailData(
            user_id=peer.user_id,
            user_name=peer.detail.user_name,
            age=peer.detail.age,
            gender=peer.detail.gender,
            nationality=peer.detail.nationality,
            travel_styles=[s.style for s in peer.travel_styles],
            friendship_id=friendship_id,
            friendship_status=friendship_status,
            is_requester=is_requester,
            i_blocked_peer=i_blocked,
            profile_image_url=peer.detail.profile_image_url,
        )
