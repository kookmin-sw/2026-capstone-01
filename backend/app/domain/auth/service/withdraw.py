from datetime import datetime, timezone, timedelta
from enum import Enum

from app.domain.auth.repository.user import UserRepository
from app.domain.auth.repository.withdrawal_request import WithdrawalRequestRepository
from app.domain.auth.model.user import UserStatus
from app.domain.auth.model.withdrawal_request import WITHDRAWAL_GRACE_PERIOD_DAYS
from app.domain.auth.service.exception import (
    WithdrawalAlreadyRequestedError,
    WithdrawalNotPendingError,
)
from app.domain.tripmate.model.tripmate_image import TripmateImage
from app.domain.tripmate.model.tripmate_post_draft import TripmatePostDraft
from app.domain.tripmate.model.tripmate_search_history import TripmateSearchHistory
from app.domain.tour.model.tour_search_history import TourSearchHistory
from app.domain.friend.model.search_history import FriendSearchHistory
from app.domain.notification.service.inbox import InboxService
from app.database.session import UnitOfWork, transactional
from app.core.object_storage import get_object_storage
from app.core.cache.redis_cache import get_redis_cache_manager
from app.core.cache.key_category import KeyCategory
from app.core.logger import get_logger


logger = get_logger("auth.withdraw")


def _registered_cache_key(user_id: str) -> str:
    return f"{KeyCategory.REGISTERED}:{user_id}"


class _PurgeOutcome(Enum):
    """worker 의 `_purge_rdb` 결과 — `purge` 가 후속 분기 결정에 사용."""
    DELETED = "deleted"        # status==INACTIVE → hard delete 완료 → 외부 정리 진행
    NO_USER = "no_user"        # RDB 에 user 없음 (이전 사이클 외부 정리 잔존) → 외부 정리 진행
    STALE_DOC = "stale_doc"    # status!=INACTIVE → cancel 복구 또는 dual-write 불일치 → doc 만 청소


async def invalidate_registered_cache(user_id: str) -> None:
    """`REGISTERED:{uid}` 캐시 무효화. 트랜잭션 commit **이후** 호출용 헬퍼.

    트랜잭션 내부에서 호출하면 commit 전에 캐시가 비워져 race 가 생긴다 — 동시 요청이
    아직 commit 되지 않은 ACTIVE 행을 읽고 캐시를 재기록 → 419 우회. 반드시 commit 후.
    """
    try:
        cache = get_redis_cache_manager()
        await cache.invalidate(_registered_cache_key(user_id))
    except Exception as e:
        # 실패해도 다음 캐시 TTL(24h) 만료 후 자연 정리 → 419 응답으로 자연 전환.
        logger.warning("REGISTERED 캐시 무효화 실패 (user_id={}): {}", user_id, e)


class WithdrawService:
    """회원 탈퇴 — 30일 유예 정책.

    진입점:
      - `request_withdraw` (HTTP DELETE /api/auth/withdraw): status 를 INACTIVE 로 전환
        + MongoDB `withdrawal_request` 컬렉션에 영구 삭제 예정 시각 적재.
      - `cancel_withdraw` (HTTP POST /api/auth/withdraw/cancel): 유예 기간 내 변심 시
        INACTIVE → ACTIVE 복구 + Mongo doc 정리.
      - `purge` (worker `app.domain.auth.worker.withdraw_purge`): 매일 KST 04:00 에
        `scheduled_purge_at` 도달분에 대해 RDB CASCADE + 외부 리소스 hard delete.

    유예 기간 동안:
      - `RegisterCheckMiddleware` 가 INACTIVE 유저의 보호 경로 접근을 419 로 차단.
      - OAuth 재로그인은 정상 진행 — 쿠키 발급 + status=WITHDRAWAL_PENDING 으로 FE 가
        cancel UI 로 라우팅. `/api/auth/withdraw/cancel` 은 prefix 제외 대상이라 419 우회.
    """

    def __init__(self, uow: UnitOfWork, inbox_service: InboxService, user_purge_cache_service):
        # user_purge_cache_service 는 chat 도메인 서비스 — type hint 생략으로 순환 import 회피
        # (friend.UserBlockService ← chat.BlockCacheService 와 동일 패턴).
        self.uow = uow
        self.inbox_service = inbox_service
        self.storage = get_object_storage()
        self.withdrawal_request_repo = WithdrawalRequestRepository()
        self._chat_purge = user_purge_cache_service


    # ──────────────────── HTTP: 탈퇴 요청 (soft) ────────────────────

    @transactional
    async def request_withdraw(self, user_id: str) -> datetime:
        """탈퇴 요청 — INACTIVE 전환 + MongoDB 적재.

        Returns:
            scheduled_purge_at: 영구 삭제 예정 시각 (UTC).

        Raises:
            ValueError: 유저 미존재.
            WithdrawalAlreadyRequestedError: 이미 INACTIVE — 중복 요청.

        실패 시:
            - RDB UPDATE 실패: @transactional 이 rollback → MongoDB 도 적재 안 됨.
            - MongoDB 적재 실패 (RDB 이후): 예외가 @transactional 까지 propagate →
              RDB rollback → 유저는 ACTIVE 로 복구. 호출자가 재시도하면 됨.

        호출 후처리: router 가 commit 이후 `invalidate_registered_cache(user_id)` 호출.
        같은 무효화를 트랜잭션 내부에서 하면 미커밋 상태의 ACTIVE 행을 다른 동시 요청이
        읽어 캐시를 재기록 → 419 우회 race 발생.
        """
        user_repo = UserRepository(self._session)

        user = await user_repo.find_by_id(user_id)
        if user is None:
            raise ValueError("존재하지 않는 유저입니다.")
        if user.status == UserStatus.INACTIVE:
            raise WithdrawalAlreadyRequestedError("이미 탈퇴가 요청된 유저입니다.")

        user.status = UserStatus.INACTIVE
        await user_repo.update(user)

        now = datetime.now(timezone.utc)
        purge_at = now + timedelta(days=WITHDRAWAL_GRACE_PERIOD_DAYS)

        # RDB-MongoDB strict atomicity 는 없지만, status=ACTIVE 가드(위) 가 통과한
        # 시점부터는 사실상 단일 호출자 → upsert 로 충분.
        await self.withdrawal_request_repo.upsert(
            user_id=user_id,
            requested_at=now,
            scheduled_purge_at=purge_at,
        )

        logger.info(
            "탈퇴 요청 접수 (user_id={}, purge_at={})", user_id, purge_at.isoformat(),
        )
        return purge_at


    async def revoke_user_chat_state(self, user_id: str) -> None:
        """`request_withdraw` post-commit 훅 — chat 활성 세션 즉시 종료.

        `invalidate_registered_cache` 와 동일 이유 (트랜잭션 내부 호출 시 미커밋 상태 race)
        로 별도 메서드로 분리되어 router 가 commit 이후 호출. INACTIVE 전환 후 TTL(90s)
        만료를 기다리지 않고 활성 WS 세션을 즉시 revoke 해 탈퇴 유저의 송수신 윈도우 차단.

        chat 도메인 키 조작은 `UserPurgeCacheService` 가 책임 — 도메인 경계 유지.
        """
        await self._chat_purge.revoke_all_sessions(user_id)


    # ──────────────────── 스케줄러: 영구 삭제 (hard) ────────────────────

    async def purge(self, user_id: str) -> None:
        """유저 영구 삭제 — RDB(CASCADE) + MongoDB + Object Storage + Redis.

        삭제 순서 (RDB 먼저 → 외부 리소스 best-effort):
            1. RDB (CASCADE): user →
                - user_detail_inform, user_travel_style
                - tripmate_post (→ tripmate_post_image, tripmate_post_like)
                - tripmate_post_like (좋아요 누른 입장)
                - favorite_place
                - friendship (requester/addressee 양측)
                - user_block (blocker/blocked 양측)
            2. MongoDB: tripmate_image, tripmate_post_draft,
                        tripmate_search_history, tour_search_history,
                        withdrawal_request (자기 자신)
            3. Object Storage: uploads/perm/{user_id}/* 전체 삭제
            4. Redis: REGISTERED 캐시 무효화 + chat 도메인 cleanup (unread:{uid} 등)

        외부 리소스(2~4)는 개별 try/except 로 격리한다. 한 단계가 실패해도 다음 단계는
        계속 진행하며, 실패는 로그로만 남겨 orphan 데이터가 남을 수 있으나 유저 참조 경로
        (RDB) 는 이미 끊겨 있어 사용자 경험에는 영향이 없다.

        **race-free 안전장치 (dual-write 잔존 + cancel 동시성)**:
            `_purge_rdb` 가 SELECT FOR UPDATE 로 row lock 을 잡고 한 트랜잭션 안에서
            status 검사 → DELETE 까지 수행. 동시에 진입한 `cancel_withdraw` 도 같은
            lock 을 경쟁하므로:
              - cancel 이 먼저 commit → worker 가 lock 획득 후 ACTIVE 확인 → STALE_DOC
                outcome → doc 만 청소, 외부 리소스 보존
              - worker 가 먼저 commit → cancel 의 SELECT 가 빈 결과 → 404
            결과적으로 ACTIVE 유저의 외부 데이터를 잘못 날리는 경로가 닫힘.

        `withdrawal_request` doc 청소:
            - DELETED / NO_USER outcome → `_purge_external` 마지막 단계에서 제거
              (외부 리소스 정리 실패 시 다음 사이클에서 재시도 가능하도록 보존되다 청소)
            - STALE_DOC outcome → 외부 리소스는 손대지 않고 doc 만 즉시 제거
        """
        outcome = await self._purge_rdb(user_id)

        if outcome == _PurgeOutcome.STALE_DOC:
            logger.warning(
                "탈퇴 영구 삭제 — RDB status 가 INACTIVE 아님 (cancel 복구 또는 "
                "dual-write 잔존), 외부 리소스 보존 + stale doc 만 정리 (user_id={})",
                user_id,
            )
            try:
                await self.withdrawal_request_repo.delete_by_user_id(user_id)
            except Exception as e:
                # 다음 사이클에서 같은 가드에 다시 걸려 재시도.
                logger.error(
                    "탈퇴 영구 삭제 — stale doc 정리 실패, 다음 tick 재시도 (user_id={}): {}",
                    user_id, e,
                )
            return

        await self._purge_external(user_id)


    @transactional
    async def _purge_rdb(self, user_id: str) -> "_PurgeOutcome":
        """RDB row lock 획득 → status 검사 → 조건부 hard delete. 단일 트랜잭션.

        Returns:
            DELETED   — status==INACTIVE 였고 hard delete 완료.
            NO_USER   — RDB 에 user 없음 (이전 사이클 외부 정리 잔존).
            STALE_DOC — status!=INACTIVE (cancel 로 복구되었거나 dual-write 잔존).
        """
        user_repo = UserRepository(self._session)
        user = await user_repo.find_by_id_for_update(user_id)

        if user is None:
            logger.info(
                "탈퇴 영구 삭제 — RDB 에 user 없음, 외부 리소스 정리만 진행 (user_id={})",
                user_id,
            )
            return _PurgeOutcome.NO_USER

        if user.status != UserStatus.INACTIVE:
            return _PurgeOutcome.STALE_DOC

        await user_repo.hard_delete_by_id(user_id)
        logger.info("탈퇴 영구 삭제 — RDB 삭제 완료 (user_id={})", user_id)
        return _PurgeOutcome.DELETED


    # ──────────────────── HTTP: 탈퇴 취소 (soft 복구) ────────────────────

    async def cancel_withdraw(self, user_id: str) -> None:
        """탈퇴 요청 취소 — INACTIVE → ACTIVE 복구 + Mongo doc 정리.

        호출 흐름: 유예 기간 내 변심 → OAuth 재로그인 → FE 가 status=withdrawal_pending
        또는 보호 경로의 419 를 받고 cancel 화면으로 라우팅 → 이 엔드포인트 호출.

        Raises:
            ValueError: 유저 미존재 (이미 worker 가 hard delete 했거나 race loss).
            WithdrawalNotPendingError: status 가 INACTIVE 가 아님 (이미 ACTIVE 등).

        race-free (cancel ↔ worker):
            `_set_active` 가 `find_by_id_for_update` 로 row lock 을 잡으므로 worker 의
            `_purge_rdb` 와 상호배타.
              - cancel 이 먼저 commit → worker 가 lock 획득 후 ACTIVE 봄 → STALE_DOC →
                외부 정리 skip + doc 만 청소
              - worker 가 먼저 commit → cancel 의 SELECT 가 빈 결과 → 404

        dual-write 안전:
            Mongo doc 삭제는 RDB commit **이후** 별도 단계에서 best-effort 로 수행.
            commit 후 Mongo 삭제가 실패하면 RDB 는 ACTIVE 인데 doc 만 잔존 → 다음
            worker 사이클에서 STALE_DOC 가드가 doc 청소. 어느 쪽으로 깨져도 영구 stuck
            상태가 만들어지지 않음.

            (Mongo 삭제를 같은 트랜잭션에 두면, 삭제는 즉시 반영되는데 직후 RDB commit
             이 실패하면 RDB 롤백 → INACTIVE + Mongo doc 없음 → worker 가 영원히 못
             보는 stuck 상태가 됨. 그래서 분리.)
        """
        await self._set_active(user_id)

        # post-commit Mongo doc 청소. 실패해도 worker STALE_DOC 가드가 다음 사이클에서 정리.
        try:
            await self.withdrawal_request_repo.delete_by_user_id(user_id)
        except Exception as e:
            logger.warning(
                "탈퇴 취소 — Mongo doc 정리 실패 (status 는 이미 ACTIVE), "
                "worker STALE_DOC 가드가 다음 사이클에서 정리 예정 (user_id={}): {}",
                user_id, e,
            )

        logger.info("탈퇴 요청 취소 (user_id={})", user_id)


    @transactional
    async def _set_active(self, user_id: str) -> None:
        """RDB 만 ACTIVE 로 복구. Mongo doc 정리는 호출자가 commit 후 별도 단계로 처리.

        Raises:
            ValueError: 유저 미존재.
            WithdrawalNotPendingError: status 가 INACTIVE 가 아님.
        """
        user_repo = UserRepository(self._session)
        user = await user_repo.find_by_id_for_update(user_id)
        if user is None:
            raise ValueError("존재하지 않는 유저입니다.")
        if user.status != UserStatus.INACTIVE:
            raise WithdrawalNotPendingError(
                f"탈퇴 요청 중인 유저가 아닙니다 (현재 status={user.status.value}).",
            )
        user.status = UserStatus.ACTIVE
        await user_repo.update(user)


    async def _purge_external(self, user_id: str) -> None:
        """MongoDB / Object Storage / Redis 정리. 단계별 best-effort."""
        # MongoDB (유저 데이터)
        try:
            await TripmateImage.find({"user_id": user_id}).delete()
            await TripmatePostDraft.find({"user_id": user_id}).delete()
            await TripmateSearchHistory.find({"user_id": user_id}).delete()
            await TourSearchHistory.find({"user_id": user_id}).delete()
            await FriendSearchHistory.find({"user_id": user_id}).delete()
            logger.info("탈퇴 영구 삭제 — MongoDB 유저 데이터 삭제 완료 (user_id={})", user_id)
        except Exception as e:
            logger.error(
                "탈퇴 영구 삭제 — MongoDB 삭제 실패, orphan 정리 필요 (user_id={}): {}",
                user_id, e,
            )

        # 인박스 cascade (recipient/actor 양쪽 매칭) — InboxService 가 self-swallow.
        # 다음 worker 사이클에서 STALE_DOC 가드가 이미 RDB 상으론 사라진 user 의 doc 만 청소
        # 하므로, 인박스 cascade 가 실패해도 stale 항목은 TTL 30일로 자연 정리되어 안전.
        await self.inbox_service.cascade_user_withdrawn(user_id)

        # Object Storage
        try:
            await self.storage.delete_by_prefix(user_id)
            logger.info("탈퇴 영구 삭제 — Object Storage 삭제 완료 (user_id={})", user_id)
        except Exception as e:
            logger.error(
                "탈퇴 영구 삭제 — Object Storage 삭제 실패, orphan 파일 정리 필요 (user_id={}): {}",
                user_id, e,
            )

        # Redis (REGISTERED 플래그 — 요청 시점에 이미 무효화되었지만 30일 사이 재로그인
        # 등으로 다시 채워졌을 가능성에 대한 방어. TTL(24h) 보다 길게 살아있을 일은 없으나
        # 보수적으로 한 번 더 정리.)
        await invalidate_registered_cache(user_id)

        # chat 도메인 데이터성 키 (unread:{user_id} 등) — TTL 없어 명시 정리 필요.
        # 도메인 경계 유지를 위해 chat 의 cleanup 훅 통해 호출.
        await self._chat_purge.cleanup_user_data(user_id)

        # withdrawal_request 자체 — 모든 정리 끝난 뒤 마지막에 제거
        try:
            await self.withdrawal_request_repo.delete_by_user_id(user_id)
        except Exception as e:
            # 이게 실패하면 다음 스케줄러 tick 에서 같은 doc 가 다시 잡혀 purge 가 재실행됨.
            # _purge_rdb 는 idempotent (user 없으면 통과), _purge_external 도 멱등 → 재실행 안전.
            logger.error(
                "탈퇴 영구 삭제 — withdrawal_request doc 삭제 실패, 다음 tick 에서 재시도 (user_id={}): {}",
                user_id, e,
            )
