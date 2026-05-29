"""MongoDB `chat_message` 리포지토리 — motor 네이티브 raw dict (이유는 model 모듈 참조)."""
from typing import Any, Optional
from pymongo import ASCENDING, DESCENDING
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from datetime import datetime

from app.domain.chat.model.chat_message import COLLECTION_NAME
from app.core.instrumentation import measure_mongo_op


class ChatMessageRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection: AsyncIOMotorCollection = db[COLLECTION_NAME]


    # ──────────────────── Create ────────────────────

    @measure_mongo_op("insert", "chat_message")
    async def insert(self, document: dict) -> None:
        """메시지 1건 insert. seq 중복은 UNIQUE 가 DuplicateKeyError 로 터트림."""
        await self.collection.insert_one(document)


    # ──────────────────── Read (단건) ────────────────────

    @measure_mongo_op("find_one", "chat_message")
    async def get_max_server_seq(self, chat_room_id: str) -> int:
        """방의 최대 server_seq (없으면 0). seq 복구 경로의 base."""
        doc = await self.collection.find_one(
            {"chat_room_id": chat_room_id},
            sort=[("server_seq", DESCENDING)],
            projection={"server_seq": 1, "_id": 0},
        )
        return int(doc["server_seq"]) if doc else 0


    # ──────────────────── Read (목록 — 히스토리 페이징) ────────────────────

    @measure_mongo_op("find", "chat_message")
    async def find_before(
        self,
        chat_room_id: str,
        before_server_seq: int,
        limit: int,
    ) -> list[dict]:
        """`seq < before` 메시지 DESC. `limit+1` 개 조회 → 호출측이 has_more 판정."""
        cursor = self.collection.find(
            {
                "chat_room_id": chat_room_id,
                "server_seq": {"$lt": before_server_seq},
            },
            sort=[("server_seq", DESCENDING)],
        ).limit(limit + 1)
        return [doc async for doc in cursor]


    @measure_mongo_op("find", "chat_message")
    async def find_after(
        self,
        chat_room_id: str,
        after_server_seq: int,
        limit: int,
    ) -> list[dict]:
        """`seq > after` 메시지 ASC. 재동기화 catch-up 용."""
        cursor = self.collection.find(
            {
                "chat_room_id": chat_room_id,
                "server_seq": {"$gt": after_server_seq},
            },
            sort=[("server_seq", ASCENDING)],
        ).limit(limit + 1)
        return [doc async for doc in cursor]


    @measure_mongo_op("find_one", "chat_message")
    async def find_by_id(self, message_id: str) -> Optional[dict]:
        """단일 메시지 조회. 편집/삭제 권한 체크용."""
        return await self.collection.find_one({"_id": message_id})


    @measure_mongo_op("find", "chat_message")
    async def find_by_ids(self, message_ids: list[str]) -> dict[str, dict]:
        """여러 `_id` 를 `{id: doc}` 으로. 방 리스트 미리보기 배치용. 누락 id 는 key 없음."""
        if not message_ids:
            return {}
        cursor = self.collection.find({"_id": {"$in": message_ids}})
        return {doc["_id"]: doc async for doc in cursor}


    @measure_mongo_op("aggregate", "chat_message")
    async def find_last_by_rooms(self, room_ids: list[str]) -> dict[str, dict]:
        """방별 최신 메시지 1건 배치 aggregate — reconcile 의 `dirty:chat_room` 처리용."""
        if not room_ids:
            return {}
        pipeline = [
            {"$match": {"chat_room_id": {"$in": room_ids}}},
            {"$sort": {"chat_room_id": 1, "server_seq": -1}},
            {"$group": {
                "_id": "$chat_room_id",
                "message_id": {"$first": "$_id"},
                "server_seq": {"$first": "$server_seq"},
                "created_at": {"$first": "$created_at"},
            }},
        ]
        cursor = self.collection.aggregate(pipeline)
        return {
            doc["_id"]: {
                "message_id": doc["message_id"],
                "server_seq": int(doc["server_seq"]),
                "created_at": doc["created_at"],
            }
            async for doc in cursor
        }


    @measure_mongo_op("count", "chat_message")
    async def count_after_seq(
        self,
        chat_room_id: str,
        after_seq: int,
        limit: int = 1000,
    ) -> int:
        """`seq > after_seq` 메시지 개수 — unread 복구 전용.

        `type != "system"` 필수 — 송신 경로가 시스템 메시지 unread 를 skip 하므로 일관성.
        `limit` 으로 N 건까지만 카운트해 999+ 캡 지원 (호출측이 `min(count, 999)` 적용).
        """
        return await self.collection.count_documents(
            {
                "chat_room_id": chat_room_id,
                "server_seq": {"$gt": after_seq},
                "type": {"$ne": "system"},
            },
            limit=limit,
            hint=[("chat_room_id", ASCENDING), ("server_seq", ASCENDING)],
        )


    # ──────────────────── Update (편집 / 삭제) ────────────────────

    @measure_mongo_op("update", "chat_message")
    async def update_content(
        self, message_id: str, new_content: Any, edited_at: datetime,
    ) -> bool:
        """본문 교체 + `edited_at` 세팅. False 면 동시성 race (service 는 find_by_id 로 pre-check)."""
        res = await self.collection.update_one(
            {"_id": message_id},
            {"$set": {"content": new_content, "edited_at": edited_at}},
        )
        return res.modified_count == 1


    @measure_mongo_op("update", "chat_message")
    async def soft_delete(self, message_id: str, deleted_at: datetime) -> bool:
        """soft delete — `deleted_at` 세팅 + `content=null`. row 자체는 보존."""
        res = await self.collection.update_one(
            {"_id": message_id},
            {"$set": {"deleted_at": deleted_at, "content": None}},
        )
        return res.modified_count == 1
