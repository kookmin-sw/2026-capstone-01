"""차단 캐시 무효화 훅.

friend 도메인의 block/unblock 후 chat 의 `room:blocks:{R}` 캐시를 무효화한다.
chat 이 자기 Redis 키 규약을 유지하도록 모든 캐시 조작은 이 파일에만 존재.

block 은 fail-closed (캐시는 다음 send_message miss 시 lazy 재구성),
unblock 은 fail-open (실패 시 ROOM_BLOCKS_TTL 후 자연 만료).
"""
from app.domain.chat.repository.chat_room import ChatRoomRepository
from app.database.session import UnitOfWork, transactional
from app.core.redis import get_redis_client
from app.core.logger import get_logger
from app.core.chat.redis_key import room_blocks_key


logger = get_logger("chat.block_cache")


class BlockCacheService:
    """chat 의 block 캐시 소유자 — friend 도메인은 이 서비스만 통해 호출."""

    def __init__(self, uow: UnitOfWork):
        self.uow = uow


    @transactional
    async def invalidate_block_cache(self, user_a: str, user_b: str) -> None:
        """두 유저의 1:1 방 `room:blocks:{R}` 를 DEL. 그룹 방은 대상 아님."""
        a, b = sorted([user_a, user_b])
        chat_room_repo = ChatRoomRepository(self._session)
        room = await chat_room_repo.find_direct_by_pair(a, b)
        if room is None:
            return

        redis = await get_redis_client()
        await redis.delete(room_blocks_key(room.chat_room_id))
        logger.info(
            "block 캐시 무효화: room_id={}, a={}, b={}", room.chat_room_id, a, b,
        )
