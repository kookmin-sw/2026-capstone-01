"""MongoDB `chat_message` 컬렉션 — motor 네이티브 사용 (low-level seq 제어가 많아 ODM 불편).

문서 스키마:
    {
        "_id":            str,              # MSG_{timestamp}_{uuid8} — 문자열 정렬 = 시간순
        "chat_room_id":   str,
        "server_seq":     int,              # 방 내부 단조 증가 시퀀스
        "sender_id":      str | None,       # 시스템 메시지는 None
        "type":           str,              # text | image | file | system
        "content":        Any,              # type 에 따라 다름 (system 은 {action, actor_id, target_ids?})
        "created_at":     datetime,
        "edited_at":      datetime | None,
        "deleted_at":     datetime | None,
    }
"""
from pymongo import ASCENDING, DESCENDING
from motor.motor_asyncio import AsyncIOMotorDatabase
import enum


COLLECTION_NAME = "chat_message"


class MessageType(str, enum.Enum):
    """MongoDB 에는 value(소문자) 로 저장."""
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    SYSTEM = "system"


async def create_indexes(db: AsyncIOMotorDatabase) -> None:
    """앱 startup 1회.

    - `{chat_room_id, server_seq}` UNIQUE — seq 중복 insert 의 DB 레벨 최종 방어선.
    - `{chat_room_id, created_at DESC}` — 시간 기반 페이징/검색용 보조.
    """
    collection = db[COLLECTION_NAME]

    await collection.create_index(
        [("chat_room_id", ASCENDING), ("server_seq", ASCENDING)],
        name="uq_chat_message_room_seq",
        unique=True,
    )
    await collection.create_index(
        [("chat_room_id", ASCENDING), ("created_at", DESCENDING)],
        name="ix_chat_message_room_created_at",
    )
