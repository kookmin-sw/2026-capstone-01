"""RoomService 단위 테스트."""
from unittest.mock import AsyncMock
from test.unit.domain.chat.room_service.model_factory import (
    ChatRoomFactory,
    UserBlockFactory,
    UserFactory,
)
from sqlalchemy.exc import IntegrityError
import pytest

from app.domain.chat.model.chat_room import ChatRoomType


# ──────────────────────────────────────────────────────────────────
# 입력 검증
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestInputValidation:
    async def test_raises_on_self(self, service):
        with pytest.raises(ValueError, match="자기 자신"):
            await service.create_direct_room(me_id="U_A", peer_user_id="U_A")


    async def test_raises_when_peer_not_found(self, service, user_repo_mock):
        user_repo_mock.find_by_id_with_profile.return_value = None

        with pytest.raises(ValueError, match="존재하지 않는 유저"):
            await service.create_direct_room(me_id="U_A", peer_user_id="U_ghost")


# ──────────────────────────────────────────────────────────────────
# 차단 관계
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestBlockRelation:
    async def test_raises_when_blocked_by_me(
        self, service, user_repo_mock, user_block_repo_mock,
    ):
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create("U_B")
        user_block_repo_mock.find_blocks_between.return_value = [
            UserBlockFactory.create(blocker_id="U_A", blocked_id="U_B"),
        ]

        with pytest.raises(ValueError, match="차단한 유저"):
            await service.create_direct_room(me_id="U_A", peer_user_id="U_B")


    async def test_raises_when_blocked_by_peer(
        self, service, user_repo_mock, user_block_repo_mock,
    ):
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create("U_B")
        user_block_repo_mock.find_blocks_between.return_value = [
            UserBlockFactory.create(blocker_id="U_B", blocked_id="U_A"),
        ]

        with pytest.raises(ValueError, match="방을 만들 수 없습니다"):
            await service.create_direct_room(me_id="U_A", peer_user_id="U_B")


# ──────────────────────────────────────────────────────────────────
# idempotent 조회 / 생성
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestIdempotentCreation:
    async def test_returns_existing_room_without_new_insert(
        self, service, user_repo_mock, chat_room_repo_mock, chat_member_repo_mock,
        fanout_mock,
    ):
        """기존 방이 있으면 재조회만 하고 fan-out/SADD 스킵."""
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create("U_B")
        existing = ChatRoomFactory.create(
            chat_room_id="CR_existing",
            direct_user_a_id="U_A",  # canonical 후 a
            direct_user_b_id="U_B",
        )
        chat_room_repo_mock.find_direct_by_pair.return_value = existing

        result = await service.create_direct_room(me_id="U_A", peer_user_id="U_B")

        assert result.chat_room_id == "CR_existing"
        chat_room_repo_mock.save.assert_not_called()
        chat_member_repo_mock.save_all.assert_not_called()
        fanout_mock.fan_out_to_user.assert_not_called()


    async def test_creates_new_room_with_canonical_order(
        self, service, user_repo_mock, chat_room_repo_mock, chat_member_repo_mock,
    ):
        """신규 생성 시 direct_user_a_id < direct_user_b_id 로 canonical."""
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create("U_A")
        chat_room_repo_mock.find_direct_by_pair.return_value = None

        saved_room = {}
        async def _save(room):
            saved_room["obj"] = room
            room.chat_room_id = "CR_new"
            return room
        chat_room_repo_mock.save.side_effect = _save

        # me=Zzz (알파벳 순 뒤) / peer=Aaa (앞) → canonical: a=Aaa, b=Zzz
        await service.create_direct_room(me_id="U_Zzz", peer_user_id="U_Aaa")

        saved: ChatRoomFactory  # type: ignore
        room = saved_room["obj"]
        assert room.direct_user_a_id == "U_Aaa"
        assert room.direct_user_b_id == "U_Zzz"
        assert room.direct_user_a_id < room.direct_user_b_id


    async def test_integrity_error_recovers_via_refind(
        self, service, user_repo_mock, chat_room_repo_mock, chat_member_repo_mock,
    ):
        """UNIQUE race (IntegrityError) 시 재조회 후 기존 방 반환."""
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create("U_A")

        # 첫 조회엔 없음 → INSERT 시도 → IntegrityError → 재조회엔 존재
        recovered = ChatRoomFactory.create(chat_room_id="CR_recovered")
        chat_room_repo_mock.find_direct_by_pair = AsyncMock(
            side_effect=[None, recovered],  # 1st: None, 2nd: 기존 방
        )
        chat_room_repo_mock.save.side_effect = IntegrityError("mock", {}, Exception())

        result = await service.create_direct_room(me_id="U_A", peer_user_id="U_B")

        assert result.chat_room_id == "CR_recovered"
        assert chat_room_repo_mock.find_direct_by_pair.await_count == 2


    async def test_integrity_error_but_still_not_found_raises(
        self, service, user_repo_mock, chat_room_repo_mock,
    ):
        """IntegrityError 이후에도 재조회 실패 시 사용자 친화 에러."""
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create("U_A")
        chat_room_repo_mock.find_direct_by_pair = AsyncMock(side_effect=[None, None])
        chat_room_repo_mock.save.side_effect = IntegrityError("mock", {}, Exception())

        with pytest.raises(ValueError, match="방 생성 경합 실패"):
            await service.create_direct_room(me_id="U_A", peer_user_id="U_B")


# ──────────────────────────────────────────────────────────────────
# 부수 효과 — fan-out / Redis
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSideEffects:
    async def test_new_room_emits_room_joined_for_both_users(
        self, service, user_repo_mock, chat_room_repo_mock, chat_member_repo_mock,
        fanout_mock,
    ):
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create("U_B")
        chat_room_repo_mock.find_direct_by_pair.return_value = None

        async def _save(room):
            room.chat_room_id = "CR_new"
            return room
        chat_room_repo_mock.save.side_effect = _save

        await service.create_direct_room(me_id="U_A", peer_user_id="U_B")

        # 양쪽에 fan_out_to_user 2회 호출
        assert fanout_mock.fan_out_to_user.await_count == 2
        targets = {call.args[0] for call in fanout_mock.fan_out_to_user.call_args_list}
        assert targets == {"U_A", "U_B"}
        for call in fanout_mock.fan_out_to_user.call_args_list:
            assert call.args[1]["type"] == "room_joined"
            assert call.args[1]["room_id"] == "CR_new"


    async def test_new_room_sadd_members_to_redis(
        self, service, user_repo_mock, chat_room_repo_mock, chat_member_repo_mock,
        redis_mock,
    ):
        user_repo_mock.find_by_id_with_profile.return_value = UserFactory.create("U_B")
        chat_room_repo_mock.find_direct_by_pair.return_value = None

        async def _save(room):
            room.chat_room_id = "CR_new"
            return room
        chat_room_repo_mock.save.side_effect = _save

        await service.create_direct_room(me_id="U_A", peer_user_id="U_B")

        # Redis pipeline 에 SADD + EXPIRE 호출 기록
        assert redis_mock._pipes, "pipeline 호출되지 않음"
        p = redis_mock._pipes[-1]
        p.sadd.assert_called_once()
        p.expire.assert_called_once()
        p.execute.assert_awaited_once()


# ──────────────────────────────────────────────────────────────────
# list_user_room_ids
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestListUserRoomIds:
    async def test_delegates_to_member_repo(self, service, chat_member_repo_mock):
        chat_member_repo_mock.find_user_room_ids.return_value = ["CR_1", "CR_2"]
        result = await service.list_user_room_ids("U_A")

        assert result == ["CR_1", "CR_2"]
        chat_member_repo_mock.find_user_room_ids.assert_awaited_once_with("U_A")
