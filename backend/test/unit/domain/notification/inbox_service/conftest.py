"""InboxService 단위 테스트 fixtures.

InboxService 는 RDB 의존성 없는 stateless service — UoW / session 받지 않음.
InboxRepository (motor 기반) 만 mock 으로 치환하면 모든 메서드 검증 가능.

`InboxItem` Document 클래스 자체도 stub 으로 치환 — service 의 fan-out 메서드가
`InboxItem(...)` 으로 직접 인스턴스화하는데, `init_beanie` 미호출 환경에서는
`CollectionWasNotInitialized` 가 raise 됨. mongo 비접근 단위 테스트라 stub 으로 우회.
"""
from test.unit.domain.notification.mock_factory import InboxRepositoryMockFactory
from test.unit.domain.notification.inbox_service.model_factory import (
    InboxItemFactory,
)
import pytest
from datetime import datetime, timezone
from beanie import PydanticObjectId

from app.domain.notification.service.inbox import InboxService


# InboxItem Document 의 pydantic field default — stub 도 동일하게 모방하여
# service 의 fan-out 결과를 진짜 Document 처럼 검증할 수 있게 한다.
_INBOX_ITEM_FIELD_DEFAULTS = {
    "comment_id": None,
    "actor_profile_image_url": None,
    "target_preview": None,
    "comment_preview": None,
    "display": True,
    "read_at": None,
}


class _InboxItemStub:
    """`InboxItem` Document 의 lightweight 대체 — 단위 테스트 전용.

    keyword-only 인스턴스화 → attribute 보유. 누락된 keyword 는 model 의 pydantic default
    를 모방해서 채움 (`comment_id=None` 등). `id` 자동 부여 (`_to_dto` 의 `str(item.id)` 대비),
    `created_at` 도 default_factory 모방.
    """

    def __init__(self, **kwargs):
        for k, v in _INBOX_ITEM_FIELD_DEFAULTS.items():
            setattr(self, k, v)
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not hasattr(self, "id") or self.id is None:
            self.id = PydanticObjectId()
        if not hasattr(self, "created_at") or self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


@pytest.fixture
def inbox_repo_mock():
    return InboxRepositoryMockFactory.create()


@pytest.fixture
def service(monkeypatch, inbox_repo_mock):
    """InboxRepository + InboxItem Document 을 stub 으로 치환한 service.

    - `InboxService.__init__` 의 `self.repo = InboxRepository()` → mock 반환.
    - service 가 호출하는 `InboxItem(...)` 은 `_InboxItemStub` 으로 대체되어
      mongo init 없이도 fan-out 흐름이 동작. mock repo 가 이 stub 을 그대로 받음.
    """
    monkeypatch.setattr(
        "app.domain.notification.service.inbox.InboxRepository",
        lambda: inbox_repo_mock,
    )
    monkeypatch.setattr(
        "app.domain.notification.service.inbox.InboxItem",
        _InboxItemStub,
    )
    return InboxService()


@pytest.fixture(autouse=True)
def reset_factories():
    """ID counter 격리 — 테스트 간 의존 방지."""
    InboxItemFactory.reset_counter()
    yield
    InboxItemFactory.reset_counter()
