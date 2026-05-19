"""회원 탈퇴 시 chat 도메인 Redis 정리 훅.

auth 도메인의 `WithdrawService` 가 두 시점에 호출:
    탈퇴 요청 commit 후       — `revoke_all_sessions`  : 활성 WS 세션 즉시 종료 (보안)
    영구 삭제 (30일 후 purge)  — `cleanup_user_data`    : 데이터성 키 정리 (위생)

chat 이 자기 Redis 키 규약 (`unread:`, `sessions:` 등) 의 소유권을 유지하도록 **모든
조작은 이 파일에만** 존재. auth 가 chat 의 키 이름 / lifecycle 을 직접 알 필요 없음.

`BlockCacheService` 와 동일 패턴 — cross-domain hook 의 anti-corruption layer.
"""
from app.domain.chat.service.session import SessionService
from app.core.redis import get_redis_client
from app.core.logger import get_logger
from app.core.chat.redis_key import unread_key


logger = get_logger("chat.user_purge_cache")


class UserPurgeCacheService:
    """chat 도메인의 회원 탈퇴 cleanup 훅 — auth 도메인 진입점."""

    def __init__(self, session_service: SessionService):
        self._session_service = session_service


    async def revoke_all_sessions(self, user_id: str) -> None:
        """탈퇴 요청 commit 후 호출 — 활성 WS 세션 즉시 종료.

        INACTIVE 전환 후 `sess:` / `ws_route:` / `sessions:` TTL(90s) 만료를 기다리지
        않고 즉시 revoke. 탈퇴 유저가 윈도우 동안 메시지 송수신 가능한 보안 risk 차단.

        실패해도 TTL 만료 후 자연 회복되므로 fail-open — 호출측 (purge worker / 라우터)
        의 핫패스를 막지 않는다.
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
        """영구 삭제 시점 호출 — TTL 없는 chat 데이터성 키 정리.

        대상:
            - `unread:{user_id}` HASH — 방별 unread count. TTL 없어 명시 정리 필요.

        다른 chat 키들은 자연 청소되므로 여기서 다루지 않음:
            - `sess:` / `ws_route:` / `sessions:` 는 TTL 90s + 탈퇴 요청 시 revoke 됨
            - `room:members:` / `room:blocks:` 는 TTL 600s + RDB CASCADE 후 캐시 워밍 시
              자연 정리 (탈퇴 유저가 SISMEMBER 대상에서 제외)
            - `rate:msg:` / `dedupe:` 는 TTL 짧음 (1s / 600s)
            - `room:seq:` 는 방 단위 카운터로 유저 cleanup 과 무관

        best-effort — 실패해도 전체 purge 흐름은 영향받지 않음.
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
