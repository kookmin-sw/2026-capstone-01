from typing import Optional
from sqlalchemy.exc import IntegrityError

from app.domain.friend.repository.user_block import UserBlockRepository
from app.domain.friend.repository.friendship import FriendshipRepository, PAGE_SIZE
from app.domain.friend.model.friendship import Friendship, FriendshipStatus
from app.domain.friend.dto.friendship import FriendshipData, FriendshipListData, FriendPeerData
from app.domain.auth.repository.user import UserRepository
from app.domain.auth.model.user import User
from app.database.session import UnitOfWork, transactional


class FriendshipService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow


    # ──────────────────── 친구 요청 ────────────────────

    @transactional
    async def send_request(self, requester_id: str, addressee_id: str) -> FriendshipData:
        """
        친구 요청 보내기

        1. 자기 자신에게 요청 불가
        2. 상대 유저 존재 검증
        3. 차단 관계 검증 (내가 차단 / 상대가 차단)
        4. 기존 friendship 검증
           - PENDING(내가 요청자): 이미 보낸 요청 → 에러
           - PENDING(상대가 요청자): 이미 와 있는 요청 → 에러 (수락 유도)
           - ACCEPTED: 이미 친구 → 에러
           - REJECTED: 재요청 허용 → upsert (방향 반전도 함께 처리)
        5. PENDING 상태로 저장
        """
        if requester_id == addressee_id:
            raise ValueError("자기 자신에게 친구 요청을 보낼 수 없습니다.")

        friendship_repo = FriendshipRepository(self._session)
        block_repo = UserBlockRepository(self._session)
        user_repo = UserRepository(self._session)

        addressee = await user_repo.find_by_id_with_profile(addressee_id)
        if addressee is None:
            raise ValueError("존재하지 않는 유저입니다.")

        # 차단 관계 우선 검증 (양방향 1 쿼리 조회 후 방향별 메시지 분기)
        # 상호 차단 시 "내가 건 차단"을 우선 안내 — 사용자가 직접 해제 가능한 쪽이 actionable
        blocks = await block_repo.find_blocks_between(requester_id, addressee_id)
        if any(b.blocker_id == requester_id for b in blocks):
            raise ValueError("차단한 유저입니다. 먼저 차단을 해제해주세요.")
        if blocks:
            raise ValueError("해당 유저에게 친구 요청을 보낼 수 없습니다.")

        existing = await friendship_repo.find_between(requester_id, addressee_id)
        if existing is not None:
            if existing.status == FriendshipStatus.PENDING:
                if existing.requester_id == requester_id:
                    raise ValueError("이미 친구 요청을 보낸 상대입니다.")
                raise ValueError("이미 친구 요청이 와 있는 상대입니다. 받은 요청에서 수락해주세요.")
            if existing.status == FriendshipStatus.ACCEPTED:
                raise ValueError("이미 친구 관계입니다.")
            # REJECTED → 재요청 허용 (기존 레코드 upsert, 방향 반전 케이스도 함께 처리)
            existing.requester_id = requester_id
            existing.addressee_id = addressee_id
            existing.status = FriendshipStatus.PENDING
            await friendship_repo.update(existing)
            # onupdate=func.now() 로 updated_at 이 expire 되므로 명시 refresh 로 async 로드
            await self._session.refresh(existing)
            return self._to_dto(existing, viewer_id=requester_id, peer=addressee)

        friendship = Friendship(
            requester_id=requester_id,
            addressee_id=addressee_id,
            status=FriendshipStatus.PENDING,
        )
        try:
            # SAVEPOINT 로 INSERT 만 감싸서 동시성 경합(같은 방향 / 반대 방향 모두)을
            # canonical unique index 위반으로 감지 → 외부 트랜잭션은 유지한 채 재조회로 복구
            async with self._session.begin_nested():
                await friendship_repo.save(friendship)
        except IntegrityError:
            existing = await friendship_repo.find_between(requester_id, addressee_id)
            if existing is None:
                raise ValueError("친구 요청을 처리하지 못했습니다. 잠시 후 다시 시도해주세요.")
            if existing.status == FriendshipStatus.PENDING:
                if existing.requester_id == requester_id:
                    raise ValueError("이미 친구 요청을 보낸 상대입니다.")
                raise ValueError("이미 친구 요청이 와 있는 상대입니다. 받은 요청에서 수락해주세요.")
            if existing.status == FriendshipStatus.ACCEPTED:
                raise ValueError("이미 친구 관계입니다.")
            raise ValueError("친구 요청 상태가 변경되었습니다. 다시 시도해주세요.")

        return self._to_dto(friendship, viewer_id=requester_id, peer=addressee)


    # ──────────────────── 친구 요청 수락 ────────────────────

    @transactional
    async def accept_request(self, friendship_id: str, user_id: str) -> None:
        """
        친구 요청 수락

        1. 친구 요청 존재 검증
        2. 수신자 본인 검증
        3. PENDING 상태 검증
        4. ACCEPTED 로 변경
        """
        friendship_repo = FriendshipRepository(self._session)

        friendship = await friendship_repo.find_by_id(friendship_id)
        if friendship is None:
            raise ValueError("존재하지 않는 친구 요청입니다.")
        if friendship.addressee_id != user_id:
            raise PermissionError("요청 수락 권한이 없습니다.")
        if friendship.status != FriendshipStatus.PENDING:
            raise ValueError("대기 중인 요청만 수락할 수 있습니다.")

        friendship.status = FriendshipStatus.ACCEPTED
        await friendship_repo.update(friendship)


    # ──────────────────── 친구 요청 거절 ────────────────────

    @transactional
    async def reject_request(self, friendship_id: str, user_id: str) -> None:
        """
        친구 요청 거절

        1. 친구 요청 존재 검증
        2. 수신자 본인 검증
        3. PENDING 상태 검증
        4. REJECTED 로 변경 (유니크 제약 유지 — 동일 방향 재요청 차단)
        """
        friendship_repo = FriendshipRepository(self._session)

        friendship = await friendship_repo.find_by_id(friendship_id)
        if friendship is None:
            raise ValueError("존재하지 않는 친구 요청입니다.")
        if friendship.addressee_id != user_id:
            raise PermissionError("요청 거절 권한이 없습니다.")
        if friendship.status != FriendshipStatus.PENDING:
            raise ValueError("대기 중인 요청만 거절할 수 있습니다.")

        friendship.status = FriendshipStatus.REJECTED
        await friendship_repo.update(friendship)


    # ──────────────────── 친구 요청 취소 (보낸 쪽) ────────────────────

    @transactional
    async def cancel_request(self, friendship_id: str, user_id: str) -> None:
        """
        내가 보낸 PENDING 요청 취소

        1. 요청 존재 검증
        2. 요청자 본인 검증
        3. PENDING 상태 검증
        4. 레코드 삭제 (취소는 히스토리 불필요)
        """
        friendship_repo = FriendshipRepository(self._session)

        friendship = await friendship_repo.find_by_id(friendship_id)
        if friendship is None:
            raise ValueError("존재하지 않는 친구 요청입니다.")
        if friendship.requester_id != user_id:
            raise PermissionError("요청 취소 권한이 없습니다.")
        if friendship.status != FriendshipStatus.PENDING:
            raise ValueError("대기 중인 요청만 취소할 수 있습니다.")

        await friendship_repo.delete(friendship)


    # ──────────────────── 친구 삭제 ────────────────────

    @transactional
    async def remove_friend(self, friendship_id: str, user_id: str) -> None:
        """
        친구 삭제 (ACCEPTED 관계에서만)

        - 요청자/수신자 양쪽 모두 삭제 가능
        """
        friendship_repo = FriendshipRepository(self._session)

        friendship = await friendship_repo.find_by_id(friendship_id)
        if friendship is None:
            raise ValueError("존재하지 않는 친구 관계입니다.")
        if user_id not in (friendship.requester_id, friendship.addressee_id):
            raise PermissionError("친구 삭제 권한이 없습니다.")
        if friendship.status != FriendshipStatus.ACCEPTED:
            raise ValueError("친구 상태에서만 삭제할 수 있습니다.")

        await friendship_repo.delete(friendship)


    # ──────────────────── 목록 조회 ────────────────────

    @transactional
    async def get_friends(self, user_id: str, cursor: Optional[str] = None) -> FriendshipListData:
        """ACCEPTED 상태의 친구 목록 (최신 수락순 30개, 커서 페이지네이션)"""
        friendship_repo = FriendshipRepository(self._session)
        items = await friendship_repo.find_friends(user_id, cursor)
        return self._to_list_dto(items, viewer_id=user_id)


    @transactional
    async def get_received_requests(self, user_id: str, cursor: Optional[str] = None) -> FriendshipListData:
        """내가 받은 PENDING 요청 목록"""
        friendship_repo = FriendshipRepository(self._session)
        items = await friendship_repo.find_received_requests(user_id, cursor)
        return self._to_list_dto(items, viewer_id=user_id)


    @transactional
    async def get_sent_requests(self, user_id: str, cursor: Optional[str] = None) -> FriendshipListData:
        """내가 보낸 PENDING 요청 목록"""
        friendship_repo = FriendshipRepository(self._session)
        items = await friendship_repo.find_sent_requests(user_id, cursor)
        return self._to_list_dto(items, viewer_id=user_id)


    # ──────────────────── 내부 변환 유틸 ────────────────────

    @staticmethod
    def _peer_of(friendship: Friendship, viewer_id: str) -> User:
        """친구 관계에서 viewer의 반대쪽 User 객체 반환 (relationship 로드 필요)"""
        if friendship.requester_id == viewer_id:
            return friendship.addressee
        return friendship.requester


    @staticmethod
    def _to_peer_dto(peer: User) -> FriendPeerData:
        detail = peer.detail
        return FriendPeerData(
            user_id=peer.user_id,
            user_name=detail.user_name,
            age=detail.age,
            gender=detail.gender,
            nationality=detail.nationality,
            profile_image_url=detail.profile_image_url,
        )


    @classmethod
    def _to_dto(cls, friendship: Friendship, viewer_id: str, peer: User) -> FriendshipData:
        return FriendshipData(
            friendship_id=friendship.friendship_id,
            status=friendship.status,
            peer=cls._to_peer_dto(peer),
            is_requester=(friendship.requester_id == viewer_id),
            created_at=friendship.created_at,
            updated_at=friendship.updated_at,
        )


    def _to_list_dto(self, items: list[Friendship], viewer_id: str) -> FriendshipListData:
        dtos = [
            self._to_dto(f, viewer_id=viewer_id, peer=self._peer_of(f, viewer_id))
            for f in items
        ]
        next_cursor = items[-1].friendship_id if len(items) == PAGE_SIZE else None
        return FriendshipListData(items=dtos, next_cursor=next_cursor)
