from typing import Iterable, Optional
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, case, func

from app.domain.friend.model.friendship import Friendship, FriendshipStatus
from app.domain.auth.model.user import User


# 친구/요청 목록 페이지 크기
PAGE_SIZE = 30


class FriendshipRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    # ──────────────────── Create ────────────────────

    async def save(self, friendship: Friendship) -> Friendship:
        """친구 관계 저장"""
        self.session.add(friendship)
        await self.session.flush()
        return friendship


    # ──────────────────── Read (단건) ────────────────────

    async def find_by_id(self, friendship_id: str) -> Optional[Friendship]:
        """friendship_id로 단건 조회"""
        return await self.session.get(Friendship, friendship_id)


    async def count_accepted_for(self, user_id: str) -> int:
        """`user_id` 의 ACCEPTED 친구 수 — 마이페이지 stats 용.

        `(requester_id, status)` / `(addressee_id, status)` 두 부분 인덱스가 모두 존재해
        PG planner 가 BitmapOr 로 처리. PENDING/REJECTED 는 제외.

        탈퇴 유저는 `users` FK CASCADE 로 친구 관계 row 가 함께 삭제되므로 dangling 없음.
        """
        stmt = select(func.count()).select_from(Friendship).where(
            Friendship.status == FriendshipStatus.ACCEPTED,
            or_(
                Friendship.requester_id == user_id,
                Friendship.addressee_id == user_id,
            ),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()


    async def find_accepted_friend_ids(self, me_id: str) -> set[str]:
        """`me_id` 의 모든 ACCEPTED 친구 user_id 집합.

        그룹 방 초대 가능 친구 후보 추출용 — 친구 ID 만 필요할 때 프로필 join 없이
        빠르게 가져와 차집합 연산에 쓴다.
        """
        peer_id = case(
            (Friendship.requester_id == me_id, Friendship.addressee_id),
            else_=Friendship.requester_id,
        )
        stmt = select(peer_id).where(
            Friendship.status == FriendshipStatus.ACCEPTED,
            or_(
                Friendship.requester_id == me_id,
                Friendship.addressee_id == me_id,
            ),
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())


    async def find_accepted_friend_ids_with(
        self, me_id: str, target_ids: Iterable[str],
    ) -> set[str]:
        """`me_id` 와 ACCEPTED 친구 관계인 `target_ids` 의 서브셋 반환.

        그룹 채팅 초대 시 "친구만 초대 가능" 정책 체크에 사용 — N 번 단발 조회를
        1 번 쿼리로 묶는다. ``block`` 발생 시 friendship 이 `UserBlockService`
        에서 삭제되므로 차단 관계도 자연히 걸러진다.
        """
        targets = list(target_ids)
        if not targets:
            return set()

        peer_id = case(
            (Friendship.requester_id == me_id, Friendship.addressee_id),
            else_=Friendship.requester_id,
        )
        stmt = select(peer_id).where(
            Friendship.status == FriendshipStatus.ACCEPTED,
            or_(
                and_(
                    Friendship.requester_id == me_id,
                    Friendship.addressee_id.in_(targets),
                ),
                and_(
                    Friendship.addressee_id == me_id,
                    Friendship.requester_id.in_(targets),
                ),
            ),
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())


    async def find_friendships_with(
        self,
        me_id: str,
        target_ids: Iterable[str],
    ) -> dict[str, "Friendship"]:
        """`me_id` 와 `target_ids` 사이의 친구 관계 (방향 무관) 일괄 조회.

        검색 결과 viewer 기준 friendship_status / is_requester 표시용 — N 단건 조회를
        1 쿼리로 묶는다. ``{peer_id: Friendship}`` 맵으로 반환하며, 관계 없는 peer 는
        dict 에 부재.
        """
        targets = list(target_ids)
        if not targets:
            return {}

        stmt = select(Friendship).where(
            or_(
                and_(
                    Friendship.requester_id == me_id,
                    Friendship.addressee_id.in_(targets),
                ),
                and_(
                    Friendship.addressee_id == me_id,
                    Friendship.requester_id.in_(targets),
                ),
            )
        )
        result = await self.session.execute(stmt)
        return {
            (f.addressee_id if f.requester_id == me_id else f.requester_id): f
            for f in result.scalars().all()
        }


    async def find_between(
        self,
        user_a_id: str,
        user_b_id: str,
    ) -> Optional[Friendship]:
        """두 유저 간의 친구 관계 (방향 무관) 단건 조회"""
        stmt = select(Friendship).where(
            or_(
                and_(
                    Friendship.requester_id == user_a_id,
                    Friendship.addressee_id == user_b_id,
                ),
                and_(
                    Friendship.requester_id == user_b_id,
                    Friendship.addressee_id == user_a_id,
                ),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


    # ──────────────────── Read (목록 — 커서 페이지네이션) ────────────────────

    async def find_friends(
        self,
        user_id: str,
        cursor: Optional[str] = None,
    ) -> list[Friendship]:
        """
        ACCEPTED 상태의 친구 목록 (requester 또는 addressee가 user_id인 경우)
        상대 프로필을 joinedload로 함께 로드
        """
        stmt = (
            select(Friendship)
            .options(
                joinedload(Friendship.requester).joinedload(User.detail),
                joinedload(Friendship.addressee).joinedload(User.detail),
            )
            .where(
                Friendship.status == FriendshipStatus.ACCEPTED,
                or_(
                    Friendship.requester_id == user_id,
                    Friendship.addressee_id == user_id,
                ),
            )
        )

        if cursor:
            cursor_sub = select(Friendship.updated_at).where(Friendship.friendship_id == cursor).scalar_subquery()
            stmt = stmt.where(
                or_(
                    Friendship.updated_at < cursor_sub,
                    (Friendship.updated_at == cursor_sub) & (Friendship.friendship_id < cursor),
                )
            )

        stmt = stmt.order_by(Friendship.updated_at.desc(), Friendship.friendship_id.desc()).limit(PAGE_SIZE)
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())


    async def find_received_requests(
        self,
        user_id: str,
        cursor: Optional[str] = None,
    ) -> list[Friendship]:
        """내가 받은 PENDING 요청 목록 (요청자 프로필 포함)"""
        stmt = (
            select(Friendship)
            .options(joinedload(Friendship.requester).joinedload(User.detail))
            .where(
                Friendship.addressee_id == user_id,
                Friendship.status == FriendshipStatus.PENDING,
            )
        )

        if cursor:
            cursor_sub = select(Friendship.updated_at).where(Friendship.friendship_id == cursor).scalar_subquery()
            stmt = stmt.where(
                or_(
                    Friendship.updated_at < cursor_sub,
                    (Friendship.updated_at == cursor_sub) & (Friendship.friendship_id < cursor),
                )
            )

        stmt = stmt.order_by(Friendship.updated_at.desc(), Friendship.friendship_id.desc()).limit(PAGE_SIZE)
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())


    async def find_sent_requests(
        self,
        user_id: str,
        cursor: Optional[str] = None,
    ) -> list[Friendship]:
        """내가 보낸 PENDING 요청 목록 (수신자 프로필 포함)"""
        stmt = (
            select(Friendship)
            .options(joinedload(Friendship.addressee).joinedload(User.detail))
            .where(
                Friendship.requester_id == user_id,
                Friendship.status == FriendshipStatus.PENDING,
            )
        )

        if cursor:
            cursor_sub = select(Friendship.updated_at).where(Friendship.friendship_id == cursor).scalar_subquery()
            stmt = stmt.where(
                or_(
                    Friendship.updated_at < cursor_sub,
                    (Friendship.updated_at == cursor_sub) & (Friendship.friendship_id < cursor),
                )
            )

        stmt = stmt.order_by(Friendship.updated_at.desc(), Friendship.friendship_id.desc()).limit(PAGE_SIZE)
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())


    # ──────────────────── Update ────────────────────

    async def update(self, friendship: Friendship) -> Friendship:
        """변경사항 flush"""
        await self.session.flush()
        return friendship


    # ──────────────────── Delete ────────────────────

    async def delete(self, friendship: Friendship) -> None:
        """친구 관계 삭제"""
        await self.session.delete(friendship)
