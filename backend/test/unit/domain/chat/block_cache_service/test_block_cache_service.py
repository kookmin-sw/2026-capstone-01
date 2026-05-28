"""BlockCacheService — friend block/unblock 의 chat 캐시 무효화 훅 단위 테스트.

검증 대상:
    - 두 유저 사이 1:1 방 존재 → `room:blocks:{R}` Redis 키 DEL
    - 1:1 방 미존재 → no-op (그룹 방은 차단 무관 → 처리 안 함)
    - canonical 정렬: 입력 순서 무관, 항상 sorted([a,b]) 로 repo 조회
"""
from test.unit.domain.chat.block_cache_service.model_factory import ChatRoomFactory
import pytest

from app.core.chat.redis_key import room_blocks_key


@pytest.mark.unit
class TestInvalidateBlockCache:
    """Tests for BlockCacheService.invalidate_block_cache."""

    async def test_no_op_when_no_direct_room(
        self, service, chat_room_repo_mock, redis_mock,
    ):
        """1:1 방 없으면 — 그룹 방 영역 외이므로 redis 미접근."""
        chat_room_repo_mock.find_direct_by_pair.return_value = None

        await service.invalidate_block_cache(user_a="USER_a", user_b="USER_b")

        redis_mock.delete.assert_not_awaited()


    async def test_deletes_redis_key_when_room_exists(
        self, service, chat_room_repo_mock, redis_mock,
    ):
        """1:1 방 존재 → `room:blocks:{R}` 키 1회 DEL."""
        room = ChatRoomFactory.create(chat_room_id="CR_xy")
        chat_room_repo_mock.find_direct_by_pair.return_value = room

        await service.invalidate_block_cache(user_a="USER_a", user_b="USER_b")

        redis_mock.delete.assert_awaited_once_with(room_blocks_key("CR_xy"))


    async def test_canonical_sort_regardless_of_input_order(
        self, service, chat_room_repo_mock,
    ):
        """입력 순서 (a, b) 와 (b, a) 모두 동일 (sorted) 인자로 repo 조회.

        block / unblock 호출자가 다른 순서로 넘겨도 같은 1:1 방을 찾도록 canonical 보장.
        """
        chat_room_repo_mock.find_direct_by_pair.return_value = None

        # 정방향 (a < b)
        await service.invalidate_block_cache(user_a="USER_a", user_b="USER_b")
        # 역방향 (b > a)
        await service.invalidate_block_cache(user_a="USER_b", user_b="USER_a")

        # 두 호출 모두 정렬된 순서 (a, b) 로 repo 조회
        assert chat_room_repo_mock.find_direct_by_pair.await_count == 2
        for await_call in chat_room_repo_mock.find_direct_by_pair.await_args_list:
            assert await_call.args == ("USER_a", "USER_b")
