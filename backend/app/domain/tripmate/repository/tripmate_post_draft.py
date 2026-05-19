from typing import Optional
from pymongo import ReturnDocument
from datetime import date, datetime, timezone

from app.domain.tripmate.model.tripmate_post_draft import TripmatePostDraft
from app.core.instrumentation import measure_mongo_op


class TripmatePostDraftRepository:

    # ──────────────────── Upsert (저장/갱신) ────────────────────

    @measure_mongo_op("update", "tripmate_post_draft")
    async def upsert(self, draft: TripmatePostDraft) -> TripmatePostDraft:
        """임시저장 upsert — single atomic operation"""
        doc = draft.model_dump(exclude={"id"})
        doc["updated_at"] = datetime.now(timezone.utc)

        # MongoDB(BSON)는 date를 지원하지 않으므로 datetime으로 변환
        for key, value in doc.items():
            if isinstance(value, date) and not isinstance(value, datetime):
                doc[key] = datetime(value.year, value.month, value.day)

        result = await TripmatePostDraft.get_motor_collection().find_one_and_update(
            {"user_id": draft.user_id},
            {"$set": doc},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        return TripmatePostDraft.model_validate(result)


    # ──────────────────── Read ────────────────────

    @measure_mongo_op("find_one", "tripmate_post_draft")
    async def find_by_user_id(self, user_id: str) -> Optional[TripmatePostDraft]:
        """유저의 임시저장 조회"""
        return await TripmatePostDraft.find_one({"user_id": user_id})


    # ──────────────────── Delete ────────────────────

    @measure_mongo_op("delete", "tripmate_post_draft")
    async def delete_by_user_id(self, user_id: str) -> None:
        """유저의 임시저장 삭제 (게시글 발행 시 또는 수동 삭제 시 호출)"""
        draft = await TripmatePostDraft.find_one({"user_id": user_id})
        if draft:
            await draft.delete()
