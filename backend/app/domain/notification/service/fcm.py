"""FCM 토큰 등록/해제 + 채팅 푸시 발송.

채팅 푸시는 fan-out 단위 → 가드/조회/발송/정리를 한 트랜잭션 + 한 multicast 로 묶어 N+1 회피.
firebase_admin SDK 가 동기라 `asyncio.to_thread` 로 감싸 이벤트 루프 비차단.
"""
from firebase_admin.exceptions import FirebaseError
from firebase_admin import messaging
import asyncio

from app.domain.notification.repository.fcm_token import FcmTokenRepository
from app.domain.notification.model.fcm_token import FcmToken
from app.domain.notification.dto.fcm_token import FcmTokenData
from app.domain.chat.repository.chat_member import ChatRoomMemberRepository
from app.domain.auth.repository.user_detail_inform import UserDetailInformRepository
from app.domain.auth.repository.user import UserRepository
from app.database.session import UnitOfWork, transactional
from app.core.logger import get_logger
from app.core.instrumentation import (
    fcm_multicast_devices_inc,
    fcm_multicast_timer,
    fcm_send_inc,
    fcm_token_purged_inc,
)
from app.core.fcm import get_fcm_app


logger = get_logger("fcm_service")


# 발신자 이름 조회 실패 (탈퇴 / detail 결손) 시 fallback.
_DEFAULT_CHAT_PUSH_TITLE = "새 메시지"


class FcmService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow


    @transactional
    async def register_token(self, *, user_id: str, token: str) -> FcmTokenData:
        """디바이스 토큰 등록.

        - 신규: 새 row
        - 동일 token 의 owner 가 다르면 교체 (계정 A→B 재로그인)
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
        """본인 소유 토큰만 삭제. 없거나 타인 소유여도 idempotent (조용히 종료)."""
        repo = FcmTokenRepository(self._session)
        existing = await repo.find_by_token(token)
        if existing is None:
            return
        if existing.user_id != user_id:
            return
        await repo.delete(existing)


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
        """채팅 새 메시지 푸시 — 한 트랜잭션 + 한 multicast 로 N명 fan-out.

        가드: 방별 (`is_left=false AND room mute 안 함`) → 전역 (`global mute 안 함`) → 토큰 일괄.
        그룹방 100명도 DB 3회 (+ 발신자 PK 1회) + FCM 1회. UnregisteredError 토큰은 bulk DELETE.

        title 미지정 시 sender 의 user_name 으로, 조회 실패 시 "새 메시지" fallback.
        """
        if not user_ids:
            return 0

        member_repo = ChatRoomMemberRepository(self._session)
        pushable_in_room = await member_repo.find_pushable_user_ids_in_room(
            chat_room_id, user_ids,
        )
        if not pushable_in_room:
            return 0

        user_repo = UserRepository(self._session)
        allowed = await user_repo.find_unmuted_user_ids(list(pushable_in_room))
        if not allowed:
            return 0

        token_repo = FcmTokenRepository(self._session)
        rows = await token_repo.find_by_user_ids(list(allowed))
        if not rows:
            return 0

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
            # 글로벌 실패 (인증/네트워크) — 토큰 정리 없이 0. 비즈는 계속.
            fcm_send_inc("chat", "global_failed")
            logger.warning(
                "FCM multicast 실패 chat_room_id={} count={} error={}",
                chat_room_id, len(tokens), e,
            )
            return 0

        fcm_send_inc("chat", "ok")

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


    async def _resolve_sender_display_name(self, sender_id: str) -> str:
        """발신자 user_id → 푸시 title. 실패 시 기본 문구 fallback (이름 조회 실패가 푸시를 막지 않도록)."""
        try:
            detail_repo = UserDetailInformRepository(self._session)
            detail = await detail_repo.find_by_user_id(sender_id)
        except Exception as e:
            logger.warning(
                "발신자 이름 조회 실패 sender_id={} error={}",
                sender_id, type(e).__name__,
            )
            return _DEFAULT_CHAT_PUSH_TITLE

        if detail is None or not detail.user_name:
            return _DEFAULT_CHAT_PUSH_TITLE
        return detail.user_name


    @staticmethod
    def _to_dto(fcm_token: FcmToken) -> FcmTokenData:
        return FcmTokenData(
            fcm_token_id=fcm_token.fcm_token_id,
            created_at=fcm_token.created_at,
        )
