"""RoomService 단위 테스트용 모델 팩토리 (SimpleNamespace 기반)."""
from typing import Optional
from types import SimpleNamespace
from datetime import datetime, timezone

from app.domain.chat.model.chat_room import ChatRoomType


class UserFactory:
    _counter = 0

    @classmethod
    def create(
        cls,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        profile_image_url: Optional[str] = None,
        detail: object = "default",
    ) -> SimpleNamespace:
        cls._counter += 1
        uid = user_id or f"USER_test_{cls._counter:04d}"
        uname = user_name or f"user{cls._counter}"
        if detail == "default":
            detail_obj = SimpleNamespace(
                user_id=uid,
                user_name=uname,
                profile_image_url=profile_image_url,
            )
        else:
            detail_obj = detail
        return SimpleNamespace(user_id=uid, detail=detail_obj)


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0


class ChatRoomFactory:
    _counter = 0

    @classmethod
    def create(
        cls,
        chat_room_id: Optional[str] = None,
        type_: ChatRoomType = ChatRoomType.DIRECT,
        direct_user_a_id: Optional[str] = "USER_a",
        direct_user_b_id: Optional[str] = "USER_b",
        creator_id: Optional[str] = "USER_a",
        created_at: Optional[datetime] = None,
    ) -> SimpleNamespace:
        cls._counter += 1
        now = created_at or datetime(2026, 4, 22, tzinfo=timezone.utc)
        return SimpleNamespace(
            chat_room_id=chat_room_id or f"CR_test_{cls._counter:04d}",
            type=type_,
            title=None,
            creator_id=creator_id,
            direct_user_a_id=direct_user_a_id,
            direct_user_b_id=direct_user_b_id,
            last_message_id=None,
            last_message_server_seq=None,
            last_message_at=None,
            created_at=now,
            updated_at=now,
            effective_last_at=now,
        )


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0


class UserBlockFactory:
    _counter = 0

    @classmethod
    def create(
        cls,
        blocker_id: str = "USER_blocker",
        blocked_id: str = "USER_blocked",
    ) -> SimpleNamespace:
        cls._counter += 1
        return SimpleNamespace(
            block_id=f"BLK_test_{cls._counter:04d}",
            blocker_id=blocker_id,
            blocked_id=blocked_id,
        )


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0
