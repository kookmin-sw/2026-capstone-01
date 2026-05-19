"""MongoDB `chat_message` 컬렉션 메타 정보 및 인덱스 초기화.

beanie 가 아닌 **motor 네이티브** 로 다루는 이유:
- 메시지 스키마가 단순하고, repository 레이어에서 직접 dict 로 읽고 쓰는 편이 pydantic 변환 비용 없음.
- server_seq 충돌 / force_jump race 등 low-level 제어가 많아 ODM 이 오히려 불편.
- UNIQUE 인덱스가 C1 방어선의 핵심이라 초기화 시점 확정 필요.

문서 스키마 (repository 가 이 형태로 insert):
    {
        "_id":            str,              # MSG_{timestamp}_{uuid8}  — 문자열 정렬 = 시간순
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
    """메시지 type 필드 값. MongoDB 에는 value(소문자) 로 저장된다."""
    TEXT = "text"
    IMAGE = "image"    
    FILE = "file"      
    SYSTEM = "system" 


async def create_indexes(db: AsyncIOMotorDatabase) -> None:
    """`chat_message` 컬렉션 인덱스 초기화. 앱 startup 시 1회 호출.

    - `{chat_room_id, server_seq}` UNIQUE — C1 방어선. Redis 복구 race 시 같은 seq 가
      두 번 insert 되는 걸 DB 레벨에서 차단. `desc` 정렬은 asc 인덱스의 reverse scan 으로 커버.
    - `{chat_room_id, created_at DESC}` — 시간 기반 페이징용. `server_seq` 기반 페이징이 주력이지만
      메시지 검색 / aggregation 시 필요.
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
