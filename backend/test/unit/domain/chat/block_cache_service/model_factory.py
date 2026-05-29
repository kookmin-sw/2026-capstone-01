"""BlockCacheService 단위 테스트용 도메인 객체 팩토리.

`find_direct_by_pair` 결과는 `ChatRoom` row — service 가 `room.chat_room_id` 만 접근.
SimpleNamespace 로 minimal stub.
"""
from typing import Optional
from types import SimpleNamespace


class ChatRoomFactory:
    _counter = 0

    @classmethod
    def create(cls, *, chat_room_id: Optional[str] = None) -> SimpleNamespace:
        cls._counter += 1
        return SimpleNamespace(
            chat_room_id=chat_room_id or f"CR_test_{cls._counter:04d}",
        )


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0
