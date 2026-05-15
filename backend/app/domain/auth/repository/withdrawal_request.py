from typing import List
from datetime import datetime

from app.core.instrumentation import measure_mongo_op
from app.domain.auth.model.withdrawal_request import WithdrawalRequest


class WithdrawalRequestRepository:
    """탈퇴 요청 MongoDB 컬렉션 접근.

    `user_id` 당 1건 정책 (모델 레벨 unique 인덱스). 적재는 항상 upsert 로,
    유예 기간 내 재요청 가드는 RDB `users.status` 에서 수행하므로 여기서는 무조건 갱신.
    """

    # ──────────────────── Upsert ────────────────────

    @measure_mongo_op("update", "withdrawal_request")
    async def upsert(
        self,
        user_id: str,
        requested_at: datetime,
        scheduled_purge_at: datetime,
    ) -> None:
        """탈퇴 요청 적재 — 동일 user_id doc 가 있으면 시각만 갱신.

        beanie ODM 의 instance.save() 대신 motor native update_one 사용 — round-trip 1 회로
        upsert + race-safe.
        """
        await WithdrawalRequest.get_motor_collection().update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "user_id": user_id,
                    "requested_at": requested_at,
                    "scheduled_purge_at": scheduled_purge_at,
                },
            },
            upsert=True,
        )


    # ──────────────────── Read ────────────────────

    @measure_mongo_op("find", "withdrawal_request")
    async def find_due(self, now: datetime) -> List[WithdrawalRequest]:
        """`scheduled_purge_at <= now` 인 모든 요청 조회.

        4시 사이클 한 번에 잡히는 건수는 보통 수~수십 건 — to_list 로 일괄 로드.
        폭증 시점에는 batch 분할이 필요하나 현재 운영 트래픽 기준으론 불필요.
        """
        return await WithdrawalRequest.find(
            WithdrawalRequest.scheduled_purge_at <= now,
        ).to_list()


    # ──────────────────── Delete ────────────────────

    @measure_mongo_op("delete", "withdrawal_request")
    async def delete_by_user_id(self, user_id: str) -> None:
        """user_id 의 탈퇴 요청 doc 삭제 — 영구 삭제 사이클의 최종 단계에서 호출.

        실패 시 doc 가 남아 다음 사이클에서 재시도되며, `purge` 자체는 멱등하므로
        재실행 안전 (RDB 가 이미 비어있으면 통과).
        """
        await WithdrawalRequest.find(
            WithdrawalRequest.user_id == user_id,
        ).delete()
