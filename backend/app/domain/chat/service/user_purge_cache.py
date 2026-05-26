"""회원 탈퇴 시 chat 도메인 Redis 정리 훅.

auth 의 `WithdrawService` 가 두 시점에 호출:
- 탈퇴 요청 commit 후: `revoke_all_sessions` (활성 세션 즉시 종료)
- 영구 삭제 시:        `cleanup_user_data`  (데이터성 키 정리)

chat 이 자기 Redis 키 규약을 유지하도록 모든 조작은 이 파일에만 존재.
"""
from app.domain.chat.service.session import SessionService
from app.core.redis import get_redis_client
from app.core.logger import get_logger
from app.core.chat.redis_key import unread_key


logger = get_logger("chat.user_purge_cache")


class UserPurgeCacheService:
    """auth 도메인 진입점 — 회원 탈퇴 cleanup 훅."""

    def __init__(self, session_service: SessionService):
        self._session_service = session_service


    async def revoke_all_sessions(self, user_id: str) -> None:
        """탈퇴 직후 활성 WS 세션 즉시 종료. TTL 만료 윈도우 동안의 송수신 보안 risk 차단.

        실패해도 TTL 로 자연 회복 — 호출측 핫패스를 막지 않는 fail-open.
        """
        try:
            count = await self._session_service.revoke_all_sessions(user_id)
            if count > 0:
                logger.info(
                    "탈퇴 요청 — chat 세션 {}개 즉시 revoke (user_id={})",
                    count, user_id,
                )
        except Exception as e:
            logger.warning(
                "탈퇴 요청 — chat 세션 revoke 실패 (TTL 만료 대기로 fallback): "
                "user_id={}, err={}",
                user_id, e,
            )


    async def cleanup_user_data(self, user_id: str) -> None:
        """영구 삭제 시점에 TTL 없는 키 정리 — 현재는 `unread:{user_id}` HASH 만 대상.

        나머지 chat 키는 TTL 또는 CASCADE 후 캐시 워밍으로 자연 정리되므로 다루지 않음.
        best-effort.
        """
        try:
            redis = await get_redis_client()
            await redis.delete(unread_key(user_id))
            logger.info("탈퇴 영구 삭제 — chat Redis 정리 완료 (user_id={})", user_id)
        except Exception as e:
            logger.warning(
                "탈퇴 영구 삭제 — chat Redis 정리 실패 (best-effort): user_id={}, err={}",
                user_id, e,
            )
