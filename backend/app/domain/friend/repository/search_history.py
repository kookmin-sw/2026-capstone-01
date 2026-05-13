from typing import List
from pymongo import ReturnDocument, ASCENDING
from datetime import datetime, timezone

from app.domain.friend.model.search_history import FriendSearchHistory
from app.core.instrumentation import measure_mongo_op


MAX_SEARCH_HISTORY = 10


class FriendSearchHistoryRepository:

    # ──────────────────── Create ────────────────────

    @measure_mongo_op("update", "friend_search_history")
    async def save(self, user_id: str, search_name: str) -> FriendSearchHistory:
        """검색어 저장

        - 동일 검색어가 이미 존재하면 시간만 갱신 (중복 방지)
        - 저장 후 최대 10개 초과 시 가장 오래된 검색어 자동 삭제
        """
        collection = FriendSearchHistory.get_motor_collection()
        now = datetime.now(timezone.utc)

        # 동일 검색어가 있으면 시간만 갱신, 없으면 새로 생성
        result = await collection.find_one_and_update(
            {"user_id": user_id, "search_name": search_name},
            {"$set": {"created_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        # 최대 개수 초과 시 가장 오래된 검색어 삭제
        await self._trim_oldest(user_id)

        return FriendSearchHistory.model_validate(result)

    async def _trim_oldest(self, user_id: str) -> None:
        """유저의 검색 기록이 MAX_SEARCH_HISTORY를 초과하면 오래된 것부터 삭제"""
        collection = FriendSearchHistory.get_motor_collection()
        count = await collection.count_documents({"user_id": user_id})

        if count > MAX_SEARCH_HISTORY:
            # 오래된 순으로 정렬하여 초과분 조회
            cursor = collection.find(
                {"user_id": user_id}
            ).sort("created_at", ASCENDING).limit(count - MAX_SEARCH_HISTORY)

            old_ids = [doc["_id"] async for doc in cursor]
            if old_ids:
                await collection.delete_many({"_id": {"$in": old_ids}})

    # ──────────────────── Read ────────────────────

    @measure_mongo_op("find", "friend_search_history")
    async def find_by_user_id(self, user_id: str) -> List[FriendSearchHistory]:
        """유저의 검색 기록 조회 (최신순, 최대 10개)"""
        return await FriendSearchHistory.find(
            {"user_id": user_id}
        ).sort("-created_at").limit(MAX_SEARCH_HISTORY).to_list()

    # ──────────────────── Delete ────────────────────

    @measure_mongo_op("delete", "friend_search_history")
    async def delete_one(self, user_id: str, search_name: str) -> None:
        """특정 검색어 1개 삭제"""
        doc = await FriendSearchHistory.find_one(
            {"user_id": user_id, "search_name": search_name}
        )
        if doc:
            await doc.delete()

    @measure_mongo_op("delete", "friend_search_history")
    async def delete_all_by_user_id(self, user_id: str) -> None:
        """유저의 검색 기록 전체 삭제"""
        await FriendSearchHistory.find(
            {"user_id": user_id}
        ).delete()
