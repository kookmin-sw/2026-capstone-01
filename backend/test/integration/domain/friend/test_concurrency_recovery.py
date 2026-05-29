"""SAVEPOINT + IntegrityError 복구 경로를 실 DB 로 검증.

Service 는 `begin_nested()` 로 INSERT 를 SAVEPOINT 로 감싸고, race 로 인한
유니크 제약 위반 시 SAVEPOINT 만 rollback 하고 외부 TX 는 유지한 채 복구
쿼리를 돌린다. 이 동작이 실제로 DB 레벨에서 성립하는지 확인한다.
"""

from sqlalchemy import select
import pytest

from app.domain.friend.service.user_block import UserBlockService
from app.domain.friend.service.friendship import FriendshipService
from app.domain.friend.repository.user_block import UserBlockRepository
from app.domain.friend.repository.friendship import FriendshipRepository
from app.domain.friend.model.user_block import UserBlock
from app.domain.friend.model.friendship import Friendship, FriendshipStatus


pytestmark = pytest.mark.integration


class TestSendRequestSavepointRecovery:
    """send_request: find_between 체크 이후 INSERT 전에 race 로 row 가 생긴 상황."""

    async def test_integrity_error_recovery_with_existing_pending(
        self, uow, seed_users, session_factory, monkeypatch
    ):
        """
        시뮬레이션:
        - DB 에는 이미 (a, b, PENDING) 존재
        - 첫 find_between 호출은 None 을 반환하도록 패치 → pre-check 통과
        - INSERT 가 canonical index 에 걸려 IntegrityError
        - SAVEPOINT rollback 후 복구 find_between (두 번째 호출) 은 실 DB 조회로 진짜 row 를 찾음
        - '이미 친구 요청을 보낸 상대' 분기로 종료

        SAVEPOINT 가 정상 동작하지 않으면 두 번째 쿼리가 aborted transaction 에서 실패한다.
        """
        a, b, _ = await seed_users(3)

        async with session_factory() as s:
            s.add(Friendship(requester_id=a, addressee_id=b, status=FriendshipStatus.PENDING))
            await s.commit()

        real_find_between = FriendshipRepository.find_between
        call_count = {"n": 0}

        async def fake_find_between(self, u1, u2):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # pre-check: race 로 인해 놓침
            return await real_find_between(self, u1, u2)  # recovery: 실 DB 조회

        monkeypatch.setattr(FriendshipRepository, "find_between", fake_find_between)

        service = FriendshipService(uow=uow)
        with pytest.raises(ValueError, match="이미 친구 요청을 보낸"):
            await service.send_request(requester_id=a, addressee_id=b)

        # 복구 쿼리가 성공했다는 것 = SAVEPOINT rollback 이 외부 TX 를 깨뜨리지 않았다는 증거
        assert call_count["n"] == 2

        # 최종 상태는 원래 row 1건만
        async with session_factory() as s:
            rows = (await s.execute(select(Friendship))).scalars().all()
        assert len(rows) == 1
        assert rows[0].requester_id == a and rows[0].addressee_id == b


class TestBlockUserTransactionIntegrity:
    """block_user: friendship 삭제를 SAVEPOINT 밖에서 flush 한 뒤 block INSERT 실패 케이스.

    올바른 설계라면 ValueError 가 @transactional 로 전파되며 외부 TX 까지 rollback,
    friendship 삭제도 되돌려져야 한다. 이 invariant 가 실제로 유지되는지 확인.
    """

    async def test_friendship_preserved_when_block_insert_fails(
        self, uow, seed_users, session_factory, monkeypatch
    ):
        from unittest.mock import AsyncMock, MagicMock
        a, b, _ = await seed_users(3)

        # 사전 세팅: 친구관계(ACCEPTED) + 차단 row 둘 다 이미 존재
        async with session_factory() as s:
            s.add(Friendship(requester_id=a, addressee_id=b, status=FriendshipStatus.ACCEPTED))
            s.add(UserBlock(blocker_id=a, blocked_id=b))
            await s.commit()

        # race: pre-check 를 우회 (has_blocker_blocked → False 로 고정)
        async def fake_check(self, blocker_id, blocked_id):
            return False

        monkeypatch.setattr(UserBlockRepository, "has_blocker_blocked", fake_check)

        block_cache_stub = MagicMock()
        block_cache_stub.invalidate_block_cache = AsyncMock()
        service = UserBlockService(uow=uow, block_cache_service=block_cache_stub)
        with pytest.raises(ValueError, match="이미 차단"):
            await service.block_user(user_id=a, target_user_id=b)

        # 외부 TX 가 rollback 되어 friendship 이 살아있어야 하고, block 은 선제 1건 그대로
        async with session_factory() as s:
            friendships = (await s.execute(select(Friendship))).scalars().all()
            blocks = (await s.execute(select(UserBlock))).scalars().all()

        assert len(friendships) == 1, "friendship 삭제가 rollback 되지 않았다 — TX 무결성 위반"
        assert friendships[0].status == FriendshipStatus.ACCEPTED
        assert len(blocks) == 1
