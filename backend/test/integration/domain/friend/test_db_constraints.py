"""DB-level 제약 검증.

Service 로직이 아닌 스키마 자체(canonical unique index, FK CASCADE)가 실제로
동작하는지를 raw INSERT / DELETE 로 확인한다. Service 레이어에서 이 제약이
사라져도 app 수준 체크 (find_between 등) 로 통과하는 것을 방지하기 위한 안전망.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, text
import pytest

from app.domain.friend.model.user_block import UserBlock
from app.domain.friend.model.friendship import Friendship, FriendshipStatus


pytestmark = pytest.mark.integration


class TestCanonicalUniqueIndex:
    """uq_friendship_canonical_pair — 방향 무관 유일성 제약."""

    async def test_same_direction_duplicate_rejected(self, seed_users, session_factory):
        a, b, _ = await seed_users(3)

        async with session_factory() as s:
            s.add(Friendship(requester_id=a, addressee_id=b, status=FriendshipStatus.PENDING))
            await s.commit()

        async with session_factory() as s:
            s.add(Friendship(requester_id=a, addressee_id=b, status=FriendshipStatus.PENDING))
            with pytest.raises(IntegrityError):
                await s.commit()


    async def test_reverse_direction_duplicate_rejected(self, seed_users, session_factory):
        """핵심: (A, B) 가 있는 상태에서 (B, A) 를 넣어도 canonical index 가 막아야 한다."""
        a, b, _ = await seed_users(3)

        async with session_factory() as s:
            s.add(Friendship(requester_id=a, addressee_id=b, status=FriendshipStatus.PENDING))
            await s.commit()

        async with session_factory() as s:
            s.add(Friendship(requester_id=b, addressee_id=a, status=FriendshipStatus.PENDING))
            with pytest.raises(IntegrityError):
                await s.commit()


class TestForeignKeyCascade:
    """User 삭제 시 관련 friendship / user_block 이 CASCADE 로 정리되는지."""

    async def test_user_delete_cascades_friendship(self, seed_users, session_factory):
        a, b, _ = await seed_users(3)
        async with session_factory() as s:
            s.add(Friendship(requester_id=a, addressee_id=b, status=FriendshipStatus.ACCEPTED))
            await s.commit()

        # ORM cascade 가 아니라 DB 레벨 ON DELETE CASCADE 를 검증하려는 것이므로 raw DELETE
        async with session_factory() as s:
            await s.execute(text("DELETE FROM users WHERE user_id = :uid"), {"uid": a})
            await s.commit()

        async with session_factory() as s:
            rows = (await s.execute(select(Friendship))).scalars().all()
        assert rows == []


    async def test_user_delete_cascades_user_block_as_blocker(self, seed_users, session_factory):
        a, b, _ = await seed_users(3)
        async with session_factory() as s:
            s.add(UserBlock(blocker_id=a, blocked_id=b))
            await s.commit()

        # ORM cascade 가 아니라 DB 레벨 ON DELETE CASCADE 를 검증하려는 것이므로 raw DELETE
        async with session_factory() as s:
            await s.execute(text("DELETE FROM users WHERE user_id = :uid"), {"uid": a})
            await s.commit()

        async with session_factory() as s:
            rows = (await s.execute(select(UserBlock))).scalars().all()
        assert rows == []


    async def test_user_delete_cascades_user_block_as_blocked(self, seed_users, session_factory):
        a, b, _ = await seed_users(3)
        async with session_factory() as s:
            s.add(UserBlock(blocker_id=a, blocked_id=b))
            await s.commit()

        async with session_factory() as s:
            await s.execute(text("DELETE FROM users WHERE user_id = :uid"), {"uid": b})
            await s.commit()

        async with session_factory() as s:
            rows = (await s.execute(select(UserBlock))).scalars().all()
        assert rows == []
