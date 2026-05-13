"""회원 탈퇴 영구 삭제 스케줄러.

매일 새벽 4시(KST) 에 깨어 `withdrawal_request` 컬렉션에서 `scheduled_purge_at <= now`
인 모든 doc 를 처리한다. 처리 단위는 1 명씩 — 한 유저의 정리가 실패해도 다음 유저로 진행.

`main.py` lifespan 에서 `start_withdraw_purge_scheduler(session_factory)` 1 회 호출,
shutdown 시 `stop_withdraw_purge_scheduler()` 호출. 패턴은 `chat.worker.reconcile` 과 동일.

설계 메모:
    - 사이클 발화 시각은 KST 04:00. 시스템 시간이 UTC 든 KST 든 무관하게 다음 KST 04:00 을
      절대 시각으로 계산해 sleep — 컨테이너 timezone 의존성 제거.
    - `WITHDRAW_PURGE_INTERVAL_SEC` env 가 설정되면 cron 모드 대신 고정 주기 모드.
      smoke / 통합 테스트에서 `1` 로 줄여 E2E 검증.
    - `purge` 자체는 `WithdrawService.purge` 위임 — 단일 진실 공급원.
"""
from __future__ import annotations
from typing import Optional
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
import os
from datetime import datetime, timezone, timedelta
import asyncio

from app.domain.auth.repository.withdrawal_request import WithdrawalRequestRepository
from app.domain.auth.service.withdraw import WithdrawService
from app.domain.notification.service.inbox import InboxService
from app.database.session import UnitOfWork
from app.core.instrumentation import withdraw_purge_run
from app.core.logger import get_logger


logger = get_logger("auth.withdraw_purge")


# ──────────────────── 튜닝 상수 ────────────────────

KST = timezone(timedelta(hours=9))

# 발화 시각 — KST 새벽 4시.
PURGE_HOUR_KST = 4

# 고정 주기 override (테스트용). 양수면 cron 모드 무시.
PURGE_INTERVAL_SEC = int(os.getenv("WITHDRAW_PURGE_INTERVAL_SEC", "0"))

# 한 사이클 내 단일 유저 purge 의 격리 타임아웃 — 외부 리소스 지연으로 사이클 전체가
# 무한 대기되는 것을 방지. 30분 정도 여유.
PURGE_PER_USER_TIMEOUT_SEC = 30 * 60

# shutdown 시 루프가 stop_event 감지 후 현재 사이클까지 마치는 데 줄 최대 유예.
PURGE_SHUTDOWN_GRACE_SEC = 30.0


# ──────────────────── 모듈 상태 ────────────────────

_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
_purge_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


def _require_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError(
            "withdraw purge 워커가 초기화되지 않았습니다. "
            "main.py lifespan 에서 start_withdraw_purge_scheduler(session_factory) 를 먼저 호출하세요.",
        )
    return _session_factory


# ──────────────────── 스케줄 계산 ────────────────────

def _seconds_until_next_fire(now_utc: datetime) -> float:
    """현재 시각에서 다음 KST 04:00 까지의 초. 이미 지났다면 다음날 04:00."""
    now_kst = now_utc.astimezone(KST)
    next_fire_kst = now_kst.replace(
        hour=PURGE_HOUR_KST, minute=0, second=0, microsecond=0,
    )
    if now_kst >= next_fire_kst:
        next_fire_kst += timedelta(days=1)
    return (next_fire_kst - now_kst).total_seconds()


# ──────────────────── 핵심 로직 ────────────────────

async def purge_due_withdrawals_once() -> int:
    """`scheduled_purge_at <= now` 인 모든 탈퇴 요청을 1 명씩 영구 삭제.

    Returns:
        이번 사이클에서 처리한 유저 수 (성공 + 실패 모두 포함).
    """
    factory = _require_factory()
    now = datetime.now(timezone.utc)

    request_repo = WithdrawalRequestRepository()
    due = await request_repo.find_due(now)

    if not due:
        logger.info("withdraw purge: 처리 대상 없음 (now={})", now.isoformat())
        return 0

    logger.info("withdraw purge: 사이클 시작 — 대상 {} 명", len(due))

    succeeded = 0
    failed = 0
    for req in due:
        # 매 유저마다 새 UoW 로 isolated. 한 유저의 RDB 트랜잭션이 다른 유저로 leak 되지 않게.
        # InboxService 는 stateless (Mongo 단독) 라 매 사이클 새로 만들어도 비용 0.
        service = WithdrawService(
            uow=UnitOfWork(session=factory),
            inbox_service=InboxService(),
        )
        try:
            await asyncio.wait_for(
                service.purge(req.user_id),
                timeout=PURGE_PER_USER_TIMEOUT_SEC,
            )
            succeeded += 1
        except asyncio.TimeoutError:
            failed += 1
            logger.error(
                "withdraw purge: 유저 처리 타임아웃 (user_id={}, timeout={}s)",
                req.user_id, PURGE_PER_USER_TIMEOUT_SEC,
            )
        except Exception as e:
            failed += 1
            logger.exception(
                "withdraw purge: 유저 처리 실패 (user_id={}): {}", req.user_id, e,
            )

    logger.info(
        "withdraw purge: 사이클 완료 — 성공 {} / 실패 {} / 전체 {}",
        succeeded, failed, len(due),
    )
    return len(due)


# ──────────────────── 주기 루프 ────────────────────

async def _purge_loop(stop_event: asyncio.Event) -> None:
    """주기 루프 — stop_event 가 set 될 때까지 무한 반복.

    cron 모드 (PURGE_INTERVAL_SEC == 0): 다음 KST 04:00 까지 sleep → 한 사이클 처리.
    고정 모드 (PURGE_INTERVAL_SEC > 0): 즉시 한 사이클 → interval sleep 반복 (테스트용).
    """
    if PURGE_INTERVAL_SEC > 0:
        logger.info(
            "withdraw purge 루프 시작: 고정 주기 모드 ({}s)", PURGE_INTERVAL_SEC,
        )
    else:
        logger.info(
            "withdraw purge 루프 시작: cron 모드 (KST 매일 {:02d}:00)", PURGE_HOUR_KST,
        )

    while not stop_event.is_set():
        # 다음 발화 시각까지 대기. stop_event 가 들어오면 즉시 종료.
        if PURGE_INTERVAL_SEC > 0:
            sleep_secs = float(PURGE_INTERVAL_SEC)
        else:
            sleep_secs = _seconds_until_next_fire(datetime.now(timezone.utc))

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=sleep_secs)
            break  # stop_event set — 루프 종료
        except asyncio.TimeoutError:
            pass  # 정상 발화

        # 발화 — 사이클 1 회.
        try:
            async with withdraw_purge_run():
                await purge_due_withdrawals_once()
        except Exception as e:
            # 사이클 전역 실패는 다음 사이클로 흘려보냄. 단일 유저 실패는 위에서 이미 격리.
            logger.exception("withdraw purge 사이클 전역 실패 (계속 진행): {}", e)

    logger.info("withdraw purge 루프 종료")


# ──────────────────── 스케줄러 훅 ────────────────────

def start_withdraw_purge_scheduler(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """앱 startup 에서 1 회 호출. 일일 purge 루프 시작 + session_factory 주입."""
    global _session_factory, _purge_task, _stop_event

    _session_factory = session_factory

    if _purge_task is not None and not _purge_task.done():
        logger.warning("withdraw purge 스케줄러 중복 시작 무시")
        return

    _stop_event = asyncio.Event()
    _purge_task = asyncio.create_task(
        _purge_loop(_stop_event),
        name="auth-withdraw-purge",
    )


async def stop_withdraw_purge_scheduler() -> None:
    """앱 shutdown 에서 호출. 루프를 graceful 종료하되 GRACE_SEC 초과 시 cancel."""
    global _purge_task, _stop_event

    task = _purge_task
    event = _stop_event
    _purge_task = None
    _stop_event = None

    if task is None or event is None:
        return

    event.set()
    try:
        await asyncio.wait_for(task, timeout=PURGE_SHUTDOWN_GRACE_SEC)
    except asyncio.TimeoutError:
        logger.warning(
            "withdraw purge 루프가 {}s 내에 종료되지 않아 강제 취소", PURGE_SHUTDOWN_GRACE_SEC,
        )
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    except Exception as e:
        logger.warning("withdraw purge 루프 종료 대기 중 예외: {}", e)
