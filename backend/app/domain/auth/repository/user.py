from typing import Optional
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.domain.auth.model.user import User, UserStatus


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session


    async def find_by_id(self, user_id: str) -> Optional[User]:
        return await self.session.get(User, user_id)


    async def find_by_id_for_update(self, user_id: str) -> Optional[User]:
        """user row 에 X-lock 을 잡으면서 조회.

        탈퇴 cancel 과 worker purge 가 동시에 진입할 때 status 검사~UPDATE 를 atomic 하게
        만들기 위해 사용. 두 트랜잭션 모두 이 메서드를 쓰면 먼저 lock 잡은 쪽이 commit
        후 lock release → 다른 쪽이 갱신된 status 를 본다.
        """
        stmt = select(User).where(User.user_id == user_id).with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


    async def find_by_provider(self, auth_provider: str, auth_provider_id: str) -> Optional[User]:
        stmt = select(User).where(
            User.auth_provider == auth_provider,
            User.auth_provider_id == auth_provider_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


    async def find_by_id_with_profile(self, user_id: str) -> Optional[User]:
        """유저 + 상세정보 + 여행스타일을 한 번에 조회"""
        stmt = select(User).options(
            joinedload(User.detail),
            joinedload(User.travel_styles),
        ).where(User.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()


    async def find_unmuted_user_ids(self, user_ids: list[str]) -> set[str]:
        """입력된 `user_ids` 중 전역 알림 차단이 아닌 id 집합.

        `notification_muted IS NOT TRUE` — NULL/False 둘 다 "차단 아님" 으로 본다
        (저장 정규화상 False 는 거의 없지만 정의상 둘 다 통과).
        """
        if not user_ids:
            return set()
        stmt = select(User.user_id).where(
            User.user_id.in_(user_ids),
            User.notification_muted.is_not(True),
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())


    async def find_active_others_with_profile(self, exclude_user_id: str) -> list[User]:
        """`exclude_user_id` 를 제외한 ACTIVE 유저 + 상세정보 + 여행스타일을 일괄 조회.

        탐색 목록용 — INACTIVE(탈퇴 유예) / SUSPENDED 유저는 노출하지 않는다.
        detail 미존재(2차 회원가입 미완료) 는 호출측에서 필터.
        """
        stmt = select(User).options(
            joinedload(User.detail),
            joinedload(User.travel_styles),
        ).where(
            User.user_id != exclude_user_id,
            User.status == UserStatus.ACTIVE,
        ).order_by(User.created_at.desc(), User.user_id.desc())
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())


    async def find_by_ids_with_profile(self, user_ids: list[str]) -> dict[str, User]:
        """여러 유저 + 상세정보 + 여행스타일을 한 번에 조회해 `{user_id: User}` 맵 반환.

        방 리스트 peer 프로필 배치용. 입력이 비면 쿼리 스킵. 누락된 id 는 결과 dict 에
        key 없음 — 호출측이 `.get()` 으로 탈퇴/부재 분기.
        """
        if not user_ids:
            return {}
        stmt = select(User).options(
            joinedload(User.detail),
            joinedload(User.travel_styles),
        ).where(User.user_id.in_(user_ids))
        result = await self.session.execute(stmt)
        return {u.user_id: u for u in result.unique().scalars().all()}


    async def save(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user


    async def update(self, user: User) -> User:
        """세션 attached 상태에서 mutate 한 user 를 즉시 flush — autoflush=False 환경 대응."""
        await self.session.flush()
        return user


    async def delete(self, user: User) -> None:
        await self.session.delete(user)


    async def hard_delete_by_id(self, user_id: str) -> bool:
        """유저 하드 탈퇴 — DB CASCADE로 연관 데이터 전체 삭제

        삭제 대상 (모두 FK ondelete="CASCADE"):
            - user_detail_inform (프로필)
            - user_travel_style (여행 스타일)
            - tripmate_post (게시글) → tripmate_post_image, tripmate_post_like
            - tripmate_post_like (좋아요 누른 입장)
            - favorite_place (즐겨찾기)
            - friendship (requester/addressee 양측)
            - user_block (blocker/blocked 양측)
        """
        stmt = delete(User).where(User.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0
