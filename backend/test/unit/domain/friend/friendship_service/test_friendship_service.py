from test.unit.domain.friend.friendship_service.model_factory import (
    FriendshipFactory,
    UserBlockFactory,
    UserFactory,
)
from sqlalchemy.exc import IntegrityError
import pytest

from app.domain.friend.model.friendship import FriendshipStatus


# ──────────────────────────────────────────────────────────────────
# send_request
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSendRequest:
    """Tests for FriendshipService.send_request."""

    async def test_raises_when_sending_to_self(self, service):
        with pytest.raises(ValueError, match="자기 자신"):
            await service.send_request(requester_id="USER_a", addressee_id="USER_a")


    async def test_raises_when_addressee_not_found(self, service, user_repo_mock):
        user_repo_mock.find_by_id_with_profile.return_value = None

        with pytest.raises(ValueError, match="존재하지 않는 유저"):
            await service.send_request(requester_id="USER_a", addressee_id="USER_b")


    async def test_raises_when_requester_blocked_addressee(
        self, service, user_repo_mock, block_repo_mock
    ):
        addressee = UserFactory.create(user_id="USER_b")
        user_repo_mock.find_by_id_with_profile.return_value = addressee
        block_repo_mock.find_blocks_between.return_value = [
            UserBlockFactory.create(blocker_id="USER_a", blocked_id="USER_b"),
        ]

        with pytest.raises(ValueError, match="차단한 유저"):
            await service.send_request(requester_id="USER_a", addressee_id="USER_b")


    async def test_raises_when_addressee_blocked_requester(
        self, service, user_repo_mock, block_repo_mock
    ):
        addressee = UserFactory.create(user_id="USER_b")
        user_repo_mock.find_by_id_with_profile.return_value = addressee
        block_repo_mock.find_blocks_between.return_value = [
            UserBlockFactory.create(blocker_id="USER_b", blocked_id="USER_a"),
        ]

        with pytest.raises(ValueError, match="요청을 보낼 수 없습니다"):
            await service.send_request(requester_id="USER_a", addressee_id="USER_b")


    async def test_raises_when_pending_request_already_sent_by_me(
        self, service, user_repo_mock, friendship_repo_mock
    ):
        addressee = UserFactory.create(user_id="USER_b")
        user_repo_mock.find_by_id_with_profile.return_value = addressee
        friendship_repo_mock.find_between.return_value = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.PENDING,
        )

        with pytest.raises(ValueError, match="이미 친구 요청을 보낸"):
            await service.send_request(requester_id="USER_a", addressee_id="USER_b")


    async def test_raises_when_pending_request_received_from_target(
        self, service, user_repo_mock, friendship_repo_mock
    ):
        addressee = UserFactory.create(user_id="USER_b")
        user_repo_mock.find_by_id_with_profile.return_value = addressee
        friendship_repo_mock.find_between.return_value = FriendshipFactory.create(
            requester_id="USER_b",  # 상대가 먼저 보냈음
            addressee_id="USER_a",
            status=FriendshipStatus.PENDING,
        )

        with pytest.raises(ValueError, match="수락해주세요"):
            await service.send_request(requester_id="USER_a", addressee_id="USER_b")


    async def test_raises_when_already_friends(
        self, service, user_repo_mock, friendship_repo_mock
    ):
        addressee = UserFactory.create(user_id="USER_b")
        user_repo_mock.find_by_id_with_profile.return_value = addressee
        friendship_repo_mock.find_between.return_value = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.ACCEPTED,
        )

        with pytest.raises(ValueError, match="이미 친구 관계"):
            await service.send_request(requester_id="USER_a", addressee_id="USER_b")


    async def test_upserts_rejected_to_pending_same_direction(
        self, service, user_repo_mock, friendship_repo_mock
    ):
        addressee = UserFactory.create(user_id="USER_b")
        user_repo_mock.find_by_id_with_profile.return_value = addressee
        existing = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.REJECTED,
        )
        friendship_repo_mock.find_between.return_value = existing

        result = await service.send_request(requester_id="USER_a", addressee_id="USER_b")

        assert existing.status == FriendshipStatus.PENDING
        assert existing.requester_id == "USER_a"
        assert existing.addressee_id == "USER_b"
        assert result.status == FriendshipStatus.PENDING
        assert result.is_requester is True
        friendship_repo_mock.update.assert_awaited_once_with(existing)
        friendship_repo_mock.save.assert_not_called()


    async def test_upserts_rejected_with_direction_swap(
        self, service, user_repo_mock, friendship_repo_mock
    ):
        """상대가 전에 내게 요청 → 내가 거절했다가 이제 반대로 요청하는 케이스."""
        addressee = UserFactory.create(user_id="USER_b")
        user_repo_mock.find_by_id_with_profile.return_value = addressee
        existing = FriendshipFactory.create(
            requester_id="USER_b",  # 원래 요청자는 상대
            addressee_id="USER_a",
            status=FriendshipStatus.REJECTED,
        )
        friendship_repo_mock.find_between.return_value = existing

        result = await service.send_request(requester_id="USER_a", addressee_id="USER_b")

        # 방향이 swap 되어야 함
        assert existing.requester_id == "USER_a"
        assert existing.addressee_id == "USER_b"
        assert existing.status == FriendshipStatus.PENDING
        assert result.is_requester is True


    async def test_creates_new_friendship_when_no_existing(
        self, service, user_repo_mock, friendship_repo_mock
    ):
        addressee = UserFactory.create(user_id="USER_b", user_name="철수")
        user_repo_mock.find_by_id_with_profile.return_value = addressee
        friendship_repo_mock.find_between.return_value = None

        result = await service.send_request(requester_id="USER_a", addressee_id="USER_b")

        friendship_repo_mock.save.assert_awaited_once()
        saved_friendship = friendship_repo_mock.save.await_args.args[0]
        assert saved_friendship.requester_id == "USER_a"
        assert saved_friendship.addressee_id == "USER_b"
        assert saved_friendship.status == FriendshipStatus.PENDING

        assert result.peer.user_id == "USER_b"
        assert result.peer.user_name == "철수"
        assert result.is_requester is True


    async def test_recovers_on_integrity_error_with_existing_pending(
        self, service, user_repo_mock, friendship_repo_mock
    ):
        """동시 INSERT 경합으로 IntegrityError 가 터지면 재조회 후 분기 메시지를 반환."""
        addressee = UserFactory.create(user_id="USER_b")
        user_repo_mock.find_by_id_with_profile.return_value = addressee

        # 1차 find_between 은 None, save 는 IntegrityError, 2차 find_between 은 PENDING(내가 요청자)
        friendship_repo_mock.find_between.side_effect = [
            None,
            FriendshipFactory.create(
                requester_id="USER_a",
                addressee_id="USER_b",
                status=FriendshipStatus.PENDING,
            ),
        ]
        friendship_repo_mock.save.side_effect = IntegrityError("stmt", {}, Exception("dup"))

        with pytest.raises(ValueError, match="이미 친구 요청을 보낸"):
            await service.send_request(requester_id="USER_a", addressee_id="USER_b")


# ──────────────────────────────────────────────────────────────────
# accept_request
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestAcceptRequest:
    """Tests for FriendshipService.accept_request."""

    async def test_raises_when_not_found(self, service, friendship_repo_mock):
        friendship_repo_mock.find_by_id.return_value = None

        with pytest.raises(ValueError, match="존재하지 않는"):
            await service.accept_request(friendship_id="FS_x", user_id="USER_a")


    async def test_raises_when_not_addressee(self, service, friendship_repo_mock):
        friendship_repo_mock.find_by_id.return_value = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.PENDING,
        )

        with pytest.raises(PermissionError, match="수락 권한"):
            await service.accept_request(friendship_id="FS_x", user_id="USER_c")


    async def test_raises_when_not_pending(self, service, friendship_repo_mock):
        friendship_repo_mock.find_by_id.return_value = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.ACCEPTED,
        )

        with pytest.raises(ValueError, match="대기 중인 요청"):
            await service.accept_request(friendship_id="FS_x", user_id="USER_b")


    async def test_updates_status_to_accepted(self, service, friendship_repo_mock):
        friendship = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.PENDING,
        )
        friendship_repo_mock.find_by_id.return_value = friendship

        await service.accept_request(friendship_id="FS_x", user_id="USER_b")

        assert friendship.status == FriendshipStatus.ACCEPTED
        friendship_repo_mock.update.assert_awaited_once_with(friendship)


# ──────────────────────────────────────────────────────────────────
# reject_request
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRejectRequest:
    """Tests for FriendshipService.reject_request."""

    async def test_raises_when_not_found(self, service, friendship_repo_mock):
        friendship_repo_mock.find_by_id.return_value = None
        with pytest.raises(ValueError, match="존재하지 않는"):
            await service.reject_request(friendship_id="FS_x", user_id="USER_b")


    async def test_raises_when_not_addressee(self, service, friendship_repo_mock):
        friendship_repo_mock.find_by_id.return_value = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.PENDING,
        )
        with pytest.raises(PermissionError, match="거절 권한"):
            await service.reject_request(friendship_id="FS_x", user_id="USER_a")


    async def test_raises_when_not_pending(self, service, friendship_repo_mock):
        friendship_repo_mock.find_by_id.return_value = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.ACCEPTED,
        )
        with pytest.raises(ValueError, match="대기 중"):
            await service.reject_request(friendship_id="FS_x", user_id="USER_b")


    async def test_updates_status_to_rejected(self, service, friendship_repo_mock):
        friendship = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.PENDING,
        )
        friendship_repo_mock.find_by_id.return_value = friendship

        await service.reject_request(friendship_id="FS_x", user_id="USER_b")

        assert friendship.status == FriendshipStatus.REJECTED
        friendship_repo_mock.update.assert_awaited_once_with(friendship)


# ──────────────────────────────────────────────────────────────────
# cancel_request
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestCancelRequest:
    """Tests for FriendshipService.cancel_request."""

    async def test_raises_when_not_found(self, service, friendship_repo_mock):
        friendship_repo_mock.find_by_id.return_value = None
        with pytest.raises(ValueError, match="존재하지 않는"):
            await service.cancel_request(friendship_id="FS_x", user_id="USER_a")


    async def test_raises_when_not_requester(self, service, friendship_repo_mock):
        friendship_repo_mock.find_by_id.return_value = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.PENDING,
        )
        with pytest.raises(PermissionError, match="취소 권한"):
            await service.cancel_request(friendship_id="FS_x", user_id="USER_b")


    async def test_raises_when_not_pending(self, service, friendship_repo_mock):
        friendship_repo_mock.find_by_id.return_value = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.REJECTED,
        )
        with pytest.raises(ValueError, match="대기 중"):
            await service.cancel_request(friendship_id="FS_x", user_id="USER_a")


    async def test_deletes_on_success(self, service, friendship_repo_mock):
        friendship = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.PENDING,
        )
        friendship_repo_mock.find_by_id.return_value = friendship

        await service.cancel_request(friendship_id="FS_x", user_id="USER_a")

        friendship_repo_mock.delete.assert_awaited_once_with(friendship)


# ──────────────────────────────────────────────────────────────────
# remove_friend
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRemoveFriend:
    """Tests for FriendshipService.remove_friend."""

    async def test_raises_when_not_found(self, service, friendship_repo_mock):
        friendship_repo_mock.find_by_id.return_value = None
        with pytest.raises(ValueError, match="존재하지 않는"):
            await service.remove_friend(friendship_id="FS_x", user_id="USER_a")


    async def test_raises_when_not_party_to_friendship(self, service, friendship_repo_mock):
        friendship_repo_mock.find_by_id.return_value = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.ACCEPTED,
        )
        with pytest.raises(PermissionError, match="삭제 권한"):
            await service.remove_friend(friendship_id="FS_x", user_id="USER_c")


    async def test_raises_when_not_accepted(self, service, friendship_repo_mock):
        friendship_repo_mock.find_by_id.return_value = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.PENDING,
        )
        with pytest.raises(ValueError, match="친구 상태"):
            await service.remove_friend(friendship_id="FS_x", user_id="USER_a")


    async def test_deletes_on_success_as_requester(self, service, friendship_repo_mock):
        friendship = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.ACCEPTED,
        )
        friendship_repo_mock.find_by_id.return_value = friendship

        await service.remove_friend(friendship_id="FS_x", user_id="USER_a")

        friendship_repo_mock.delete.assert_awaited_once_with(friendship)


    async def test_deletes_on_success_as_addressee(self, service, friendship_repo_mock):
        friendship = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.ACCEPTED,
        )
        friendship_repo_mock.find_by_id.return_value = friendship

        await service.remove_friend(friendship_id="FS_x", user_id="USER_b")

        friendship_repo_mock.delete.assert_awaited_once_with(friendship)


# ──────────────────────────────────────────────────────────────────
# 목록 조회
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetFriends:
    """Tests for FriendshipService.get_friends."""

    async def test_returns_empty_list(self, service, friendship_repo_mock):
        friendship_repo_mock.find_friends.return_value = []

        result = await service.get_friends(user_id="USER_a")

        assert result.items == []
        assert result.next_cursor is None


    async def test_maps_peer_from_opposite_side(self, service, friendship_repo_mock):
        viewer = UserFactory.create(user_id="USER_a")
        peer = UserFactory.create(user_id="USER_b", user_name="영희")
        friendship = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.ACCEPTED,
            requester=viewer,
            addressee=peer,
        )
        friendship_repo_mock.find_friends.return_value = [friendship]

        result = await service.get_friends(user_id="USER_a")

        assert len(result.items) == 1
        assert result.items[0].peer.user_id == "USER_b"
        assert result.items[0].peer.user_name == "영희"
        assert result.items[0].is_requester is True
        assert result.next_cursor is None


    async def test_next_cursor_when_page_full(self, service, friendship_repo_mock):
        from app.domain.friend.repository.friendship import PAGE_SIZE

        items = []
        for i in range(PAGE_SIZE):
            viewer = UserFactory.create(user_id="USER_a")
            peer = UserFactory.create(user_id=f"USER_p{i}")
            items.append(
                FriendshipFactory.create(
                    friendship_id=f"FS_{i:03d}",
                    requester_id="USER_a",
                    addressee_id=f"USER_p{i}",
                    status=FriendshipStatus.ACCEPTED,
                    requester=viewer,
                    addressee=peer,
                )
            )
        friendship_repo_mock.find_friends.return_value = items

        result = await service.get_friends(user_id="USER_a")

        assert len(result.items) == PAGE_SIZE
        assert result.next_cursor == items[-1].friendship_id


@pytest.mark.unit
class TestGetReceivedRequests:
    """Tests for FriendshipService.get_received_requests."""

    async def test_maps_requester_as_peer(self, service, friendship_repo_mock):
        requester = UserFactory.create(user_id="USER_b", user_name="요청자")
        friendship = FriendshipFactory.create(
            requester_id="USER_b",
            addressee_id="USER_a",
            status=FriendshipStatus.PENDING,
            requester=requester,
        )
        friendship_repo_mock.find_received_requests.return_value = [friendship]

        result = await service.get_received_requests(user_id="USER_a")

        assert len(result.items) == 1
        assert result.items[0].peer.user_id == "USER_b"
        assert result.items[0].is_requester is False


@pytest.mark.unit
class TestGetSentRequests:
    """Tests for FriendshipService.get_sent_requests."""

    async def test_maps_addressee_as_peer(self, service, friendship_repo_mock):
        addressee = UserFactory.create(user_id="USER_b", user_name="수신자")
        friendship = FriendshipFactory.create(
            requester_id="USER_a",
            addressee_id="USER_b",
            status=FriendshipStatus.PENDING,
            addressee=addressee,
        )
        friendship_repo_mock.find_sent_requests.return_value = [friendship]

        result = await service.get_sent_requests(user_id="USER_a")

        assert len(result.items) == 1
        assert result.items[0].peer.user_id == "USER_b"
        assert result.items[0].is_requester is True
