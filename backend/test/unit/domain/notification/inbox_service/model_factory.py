"""InboxService 단위 테스트용 도메인 객체 팩토리.

beanie Document `InboxItem` 을 직접 인스턴스화하면 `init_beanie` 미호출 환경에서
`CollectionWasNotInitialized` 가 raise 됨 (motor_collection 접근). 단위 테스트는 mongo
비접근이므로 friend / chat 도메인의 SimpleNamespace 패턴과 동일하게 attribute 흉내내는
가벼운 객체로 대체 — service 의 `_to_dto` 가 attribute 만 접근하므로 동작에 영향 없음.
"""
from typing import Optional
from types import SimpleNamespace
from datetime import datetime, timezone
from beanie import PydanticObjectId

from app.domain.notification.model.inbox import InboxItemType, TargetType


class InboxItemFactory:
    _counter = 0

    @classmethod
    def create(
        cls,
        *,
        inbox_item_id: Optional[PydanticObjectId] = None,
        recipient_id: str = "USER_recipient",
        actor_id: str = "USER_actor",
        type: InboxItemType = InboxItemType.FEED_LIKE,
        target_type: TargetType = TargetType.FEED_POST,
        target_id: str = "FDP_test",
        comment_id: Optional[str] = None,
        actor_name: str = "actor",
        actor_profile_image_url: Optional[str] = None,
        target_preview: Optional[str] = None,
        comment_preview: Optional[str] = None,
        display: bool = True,
        read_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
    ) -> SimpleNamespace:
        cls._counter += 1
        return SimpleNamespace(
            id=inbox_item_id or PydanticObjectId(),
            recipient_id=recipient_id,
            actor_id=actor_id,
            type=type,
            target_type=target_type,
            target_id=target_id,
            comment_id=comment_id,
            actor_name=actor_name,
            actor_profile_image_url=actor_profile_image_url,
            target_preview=target_preview,
            comment_preview=comment_preview,
            display=display,
            read_at=read_at,
            created_at=created_at or datetime.now(timezone.utc),
        )


    @classmethod
    def reset_counter(cls) -> None:
        cls._counter = 0
