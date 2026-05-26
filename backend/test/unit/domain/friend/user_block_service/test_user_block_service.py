from test.unit.domain.friend.user_block_service.model_factory import (
    FriendshipFactory,
    UserBlockFactory,
    UserFactory,
)
from sqlalchemy.exc import IntegrityError
import pytest

from app.domain.friend.model.friendship import FriendshipStatus


# ──────────────────────────────────────────────────────────────────
# block_user
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestBlockUser:
    """Tests for UserBlockService.block_user."""

    async def test_raises_when_blocking_self(self, service):
        with pytest.raises(ValueError, match="자기 자신"):
            await service.block_user(user_id="USER_a", target_user_id="USER_a")


    async def test_raises_when_target_not_found(self, service, user_repo_mock):
        user_repo_mock.find_by_id_with_profile.return_value = None

        with pytest.raises(ValueError, match="존재하지 않는"):
            await service.block_user(user_id="USER_a", target_user_id="USER_b")


    async def test_raises_when_already_blocked(
        self, service, user_repo_mock, block_repo_mock
    ):
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create(user_id="USER_b")
        block_repo_mock.has_blocker_blocked.return_value = True

        with pytest.raises(ValueError, match="이미 차단"):
            await service.block_user(user_id="USER_a", target_user_id="USER_b")


    async def test_deletes_existing_friendship_then_saves_block(
        self, service, user_repo_mock, block_repo_mock, friendship_repo_mock
    ):
        target = UserFactory.create(user_id="USER_b", user_name="철수")
        user_repo_mock.find_by_id_with_profile.return_value = target
        block_repo_mock.has_blocker_blocked.return_value = False

        existing_friendship = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.ACCEPTED,
        )
        friendship_repo_mock.find_between.return_value = existing_friendship

        result = await service.block_user(user_id="USER_a", target_user_id="USER_b")

        friendship_repo_mock.delete.assert_awaited_once_with(existing_friendship)
        block_repo_mock.save.assert_awaited_once()
        saved = block_repo_mock.save.await_args.args[0]
        assert saved.blocker_id == "USER_a"
        assert saved.blocked_id == "USER_b"

        assert result.blocked.user_id == "USER_b"
        assert result.blocked.user_name == "철수"


    async def test_saves_block_without_existing_friendship(
        self, service, user_repo_mock, block_repo_mock, friendship_repo_mock
    ):
        target = UserFactory.create(user_id="USER_b")
        user_repo_mock.find_by_id_with_profile.return_value = target
        block_repo_mock.has_blocker_blocked.return_value = False
        friendship_repo_mock.find_between.return_value = None

        result = await service.block_user(user_id="USER_a", target_user_id="USER_b")

        friendship_repo_mock.delete.assert_not_called()
        block_repo_mock.save.assert_awaited_once()
        assert result.blocked.user_id == "USER_b"


    async def test_raises_on_integrity_error_when_block_exists(
        self, service, user_repo_mock, block_repo_mock, friendship_repo_mock
    ):
        """동시 INSERT 경합으로 IntegrityError → 재조회 후 이미 차단 메시지."""
        target = UserFactory.create(user_id="USER_b")
        user_repo_mock.find_by_id_with_profile.return_value = target
        block_repo_mock.has_blocker_blocked.return_value = False
        friendship_repo_mock.find_between.return_value = None

        block_repo_mock.save.side_effect = IntegrityError("stmt", {}, Exception("dup"))
        block_repo_mock.find_by_pair.return_value = UserBlockFactory.create(
            blocker_id="USER_a",
            blocked_id="USER_b",
        )

        with pytest.raises(ValueError, match="이미 차단"):
            await service.block_user(user_id="USER_a", target_user_id="USER_b")


# ──────────────────────────────────────────────────────────────────
# unblock_user
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestUnblockUser:
    """Tests for UserBlockService.unblock_user."""

    async def test_raises_when_not_blocked(self, service, block_repo_mock):
        block_repo_mock.find_by_pair.return_value = None

        with pytest.raises(ValueError, match="차단 상태가 아닙니다"):
            await service.unblock_user(user_id="USER_a", target_user_id="USER_b")


    async def test_deletes_on_success(self, service, block_repo_mock):
        block = UserBlockFactory.create(blocker_id="USER_a", blocked_id="USER_b")
        block_repo_mock.find_by_pair.return_value = block

        await service.unblock_user(user_id="USER_a", target_user_id="USER_b")

        block_repo_mock.delete.assert_awaited_once_with(block)


# ──────────────────────────────────────────────────────────────────
# get_blocked_users
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetBlockedUsers:
    """Tests for UserBlockService.get_blocked_users."""

    async def test_returns_empty_list(self, service, block_repo_mock):
        block_repo_mock.find_blocks_by_user.return_value = []

        result = await service.get_blocked_users(user_id="USER_a")

        assert result.items == []
        assert result.next_cursor is None


    async def test_maps_blocked_profile(self, service, block_repo_mock):
        peer = UserFactory.create(user_id="USER_b", user_name="영희")
        block = UserBlockFactory.create(
            blocker_id="USER_a",
            blocked_id="USER_b",
            blocked=peer,
        )
        block_repo_mock.find_blocks_by_user.return_value = [block]

        result = await service.get_blocked_users(user_id="USER_a")

        assert len(result.items) == 1
        assert result.items[0].blocked.user_id == "USER_b"
        assert result.items[0].blocked.user_name == "영희"


    async def test_next_cursor_when_page_full(self, service, block_repo_mock):
        from app.domain.friend.repository.user_block import PAGE_SIZE

        items = []
        for i in range(PAGE_SIZE):
            peer = UserFactory.create(user_id=f"USER_p{i}")
            items.append(
                UserBlockFactory.create(
                    block_id=f"BLK_{i:03d}",
                    blocker_id="USER_a",
                    blocked_id=f"USER_p{i}",
                    blocked=peer,
                )
            )
        block_repo_mock.find_blocks_by_user.return_value = items

        result = await service.get_blocked_users(user_id="USER_a")

        assert len(result.items) == PAGE_SIZE
        assert result.next_cursor == items[-1].block_id
