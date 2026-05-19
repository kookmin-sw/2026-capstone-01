from firebase_admin.exceptions import FirebaseError
from firebase_admin import messaging
import asyncio

from app.domain.notification.repository.fcm_token import FcmTokenRepository
from app.domain.notification.model.fcm_token import FcmToken
from app.domain.notification.dto.fcm_token import FcmTokenData
from app.domain.chat.repository.chat_member import ChatRoomMemberRepository
from app.domain.auth.repository.user import UserRepository
from app.domain.auth.repository.user_detail_inform import UserDetailInformRepository
from app.database.session import UnitOfWork, transactional
from app.core.logger import get_logger
from app.core.fcm import get_fcm_app
from app.core.instrumentation import (
    fcm_multicast_devices_inc,
    fcm_multicast_timer,
    fcm_send_inc,
    fcm_token_purged_inc,
)


logger = get_logger("fcm_service")


# 발신자 이름 조회 실패(탈퇴/detail 결손) 시 푸시 title fallback.
_DEFAULT_CHAT_PUSH_TITLE = "새 메시지"


class FcmService:
    """FCM 토큰 등록/해제 + 푸시 발송 서비스.

    - 발송은 채팅방 fan-out 단위 → 가드/조회/발송/정리를 **한 트랜잭션 + 한 multicast**
      로 묶어 N+1 을 회피한다 (그룹방 100명도 DB 쿼리 3회 + FCM 호출 1회로 끝).
    - `UnregisteredError` 토큰은 응답 후 bulk delete 로 즉시 정리.
    - `firebase_admin.messaging` 은 동기 SDK 라 `asyncio.to_thread` 로 감싸
      이벤트 루프를 막지 않는다.
    """

    def __init__(self, uow: UnitOfWork):
        self.uow = uow


    # ──────────────────── 토큰 등록 / 해제 ────────────────────

    @transactional
    async def register_token(self, *, user_id: str, token: str) -> FcmTokenData:
        """디바이스 토큰 등록.

        - 신규 토큰: 새 row 저장
        - 동일 token 이 다른 user 로 등록되어 있음: owner 만 교체
          (한 디바이스에서 계정 A → B 로 재로그인한 케이스)
        - 동일 (user, token) 재등록: no-op
        """
        repo = FcmTokenRepository(self._session)

        existing = await repo.find_by_token(token)
        if existing is None:
            saved = await repo.save(FcmToken(user_id=user_id, token=token))
            return self._to_dto(saved)

        if existing.user_id != user_id:
            existing.user_id = user_id
            updated = await repo.update(existing)
            return self._to_dto(updated)

        return self._to_dto(existing)


    @transactional
    async def unregister_token(self, *, user_id: str, token: str) -> None:
        """디바이스 토큰 해제 — 클라이언트 명시적 로그아웃 시점.

        본인 소유 토큰만 삭제 가능. 존재하지 않거나 이미 다른 사용자 소유로
        넘어간 토큰을 넘겨도 idempotent 하게 동작 (조용히 종료).
        """
        repo = FcmTokenRepository(self._session)
        existing = await repo.find_by_token(token)
        if existing is None:
            return
        if existing.user_id != user_id:
            return
        await repo.delete(existing)


    # ──────────────────── 채팅 푸시 (bulk) ────────────────────

    @transactional
    async def send_chat_push(
        self,
        *,
        user_ids: list[str],
        chat_room_id: str,
        sender_id: str,
        body: str,
        title: str | None = None,
    ) -> int:
        """채팅 새 메시지 푸시 — N 명에게 한 트랜잭션 + 한 multicast 로 fan-out.

        가드 체인 (SQL `IN` 으로 일괄 적용):
          1. 방별 — `chat_room_member`: `is_left=false` AND `notification_muted IS NOT TRUE`
          2. 전역 — `users.notification_muted IS NOT TRUE`
          3. 위 둘을 통과한 user 들의 모든 FCM 토큰을 모아 `MulticastMessage` 1회
          4. `UnregisteredError` 토큰은 bulk DELETE 로 정리

        그룹방 100명도 DB 쿼리 3회 (+ 발신자 이름 PK SELECT 1회) + FCM 호출 1회로 끝.

        Args:
            user_ids: 발송 후보. 보통 발신자 제외한 방의 활성 멤버 목록.
            chat_room_id, sender_id, body: 알림 내용. data 페이로드 자동 빌드.
            title: 명시되면 그대로 사용. None 이면 `sender_id` 의 `user_name` 을 조회해
                title 로 사용하고, 조회 실패(탈퇴/detail 결손) 시 `"새 메시지"` 로 폴백.
        Returns:
            multicast 성공 디바이스 수 (모두 차단됐거나 토큰 없으면 0).
        """
        if not user_ids:
            return 0

        # (1) 방별 가드 — is_left=false AND room mute 안 함
        member_repo = ChatRoomMemberRepository(self._session)
        pushable_in_room = await member_repo.find_pushable_user_ids_in_room(
            chat_room_id, user_ids,
        )
        if not pushable_in_room:
            return 0

        # (2) 전역 가드 — global mute 안 함
        user_repo = UserRepository(self._session)
        allowed = await user_repo.find_unmuted_user_ids(list(pushable_in_room))
        if not allowed:
            return 0

        # (3) 토큰 일괄 조회
        token_repo = FcmTokenRepository(self._session)
        rows = await token_repo.find_by_user_ids(list(allowed))
        if not rows:
            return 0

        # title 결정 — 호출부가 지정하지 않은 일반 채팅 푸시는 발신자 이름을 title 로.
        #   PK 조회라 비용 미미. 어떤 사유로든 이름을 못 가져오면 기본 문구로 폴백.
        final_title = title if title is not None else (
            await self._resolve_sender_display_name(sender_id)
        )

        tokens = [r.token for r in rows]
        data = {
            "type": "chat",
            "chatRoomId": chat_room_id,
            "senderId": sender_id,
            "url": f"/chat/{chat_room_id}",
        }
        multicast = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=final_title, body=body),
            data=data,
        )

        try:
            async with fcm_multicast_timer("chat"):
                batch = await asyncio.to_thread(
                    messaging.send_each_for_multicast, multicast, app=get_fcm_app(),
                )
        except FirebaseError as e:
            # 글로벌 실패 (인증/네트워크) — 토큰 정리 없이 0 반환. 비즈는 계속.
            fcm_send_inc("chat", "global_failed")
            logger.warning(
                "FCM multicast 실패 chat_room_id={} count={} error={}",
                chat_room_id, len(tokens), e,
            )
            return 0

        fcm_send_inc("chat", "ok")

        # (4) 디바이스별 결과 집계 + 만료 토큰 bulk 정리
        success_count = 0
        failed_unregistered = 0
        failed_other = 0
        invalid_tokens: list[str] = []
        for token, resp in zip(tokens, batch.responses):
            if resp.success:
                success_count += 1
                continue
            err = resp.exception
            if isinstance(err, messaging.UnregisteredError):
                failed_unregistered += 1
                invalid_tokens.append(token)
            else:
                failed_other += 1
                logger.warning(
                    "FCM 발송 실패 chat_room_id={} token_prefix={} error={}",
                    chat_room_id, token[:16], err,
                )

        fcm_multicast_devices_inc(
            success=success_count,
            failed_unregistered=failed_unregistered,
            failed_other=failed_other,
        )

        if invalid_tokens:
            await token_repo.delete_by_tokens(invalid_tokens)
            fcm_token_purged_inc(len(invalid_tokens))
            logger.info(
                "FCM 만료 토큰 정리 chat_room_id={} count={}",
                chat_room_id, len(invalid_tokens),
            )

        return batch.success_count


    # ──────────────────── 발신자 이름 해석 ────────────────────

    async def _resolve_sender_display_name(self, sender_id: str) -> str:
        """발신자 user_id → 푸시 title 로 쓸 이름. 실패 시 기본 문구로 폴백.

        같은 @transactional 세션에서 PK 로 1건 SELECT — `find_unmuted_user_ids` 등
        다른 가드 쿼리와 동일 트랜잭션이라 추가 커넥션 비용 없음.
        """
        try:
            detail_repo = UserDetailInformRepository(self._session)
            detail = await detail_repo.find_by_user_id(sender_id)
        except Exception as e:
            # 이름 조회 실패가 푸시 자체를 막아선 안 된다 — 기본 문구로 진행. 예를 들어 탈퇴는 하는 동시에 채팅을 보냈을 때
            logger.warning(
                "발신자 이름 조회 실패 sender_id={} error={}",
                sender_id, type(e).__name__,
            )
            return _DEFAULT_CHAT_PUSH_TITLE

        if detail is None or not detail.user_name:
            return _DEFAULT_CHAT_PUSH_TITLE
        return detail.user_name


    # ──────────────────── 변환 ────────────────────

    @staticmethod
    def _to_dto(fcm_token: FcmToken) -> FcmTokenData:
        return FcmTokenData(
            fcm_token_id=fcm_token.fcm_token_id,
            created_at=fcm_token.created_at,
        )
