"""차단 캐시 무효화 훅

friend 도메인이 block/unblock 을 처리할 때 이 서비스를 호출해 chat 쪽의
`room:blocks:{R}` Redis 캐시를 무효화한다. chat 이 자기 Redis 키 규약(키 이름, 포맷)의
소유권을 유지하도록 **모든 캐시 조작은 이 파일에만** 존재.

호출 계약:
    block  : `UserBlockService.block_user`   — DB INSERT → `invalidate_block_cache`
             (fail-closed. 캐시 warm-up 은 lazy: 다음 send_message 가 miss 시 재구성)
    unblock: `UserBlockService.unblock_user` — `invalidate_block_cache` → DB DELETE
             (fail-open. 캐시 삭제만 실패하면 `ROOM_BLOCKS_TTL` 후 자연 만료)

두 유저 사이에 1:1 방이 없으면 할 일 없음 — 그룹 방은 차단과 무관하므로 대상에서 제외.
"""
from app.domain.chat.repository.chat_room import ChatRoomRepository
from app.database.session import UnitOfWork, transactional
from app.core.redis import get_redis_client
from app.core.logger import get_logger
from app.core.chat.redis_key import room_blocks_key


logger = get_logger("chat.block_cache")


class BlockCacheService:
    """chat 도메인의 block 캐시 소유자. friend 도메인은 이 서비스만 통해 훅을 호출."""

    def __init__(self, uow: UnitOfWork):
        self.uow = uow


    @transactional
    async def invalidate_block_cache(self, user_a: str, user_b: str) -> None:
        """두 유저의 1:1 방 `room:blocks:{R}` 를 DEL.

        canonical 정렬 후 `ChatRoomRepository.find_direct_by_pair` 로 단건 조회 —
        1:1 방은 `(a<b)` 쌍당 UNIQUE 제약이 있어 최대 1개 방만 영향 대상이다.
        방이 없으면 no-op. Redis 실패는 호출측 결정 (fail-open 정책에선 삼킨다).
        """
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
