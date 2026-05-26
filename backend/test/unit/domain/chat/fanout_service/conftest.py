from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
import pytest

from app.domain.chat.service.fanout import FanoutService


def make_ws(session_id: str, user_id: str) -> MagicMock:
    """FanoutService 가 duck typing 으로 기대하는 WS 객체.

    - `session_id` / `user_id` / `subscribed_rooms` 속성
    - `send_json` 은 AsyncMock
    """
    ws = MagicMock(name=f"ws-{session_id}")
    ws.session_id = session_id
    ws.user_id = user_id
    ws.subscribed_rooms = set()
    ws.send_json = AsyncMock()
    return ws


@pytest.fixture
def fanout(monkeypatch) -> FanoutService:
    """FANOUT_MODE=in_process 를 명시 고정해 로컬 .env 오버라이드(node_channel)
    영향으로 실제 Redis 연결을 시도하지 않도록 한다.
    """
    from app.config import setting as setting_module
    monkeypatch.setattr(setting_module.settings, "FANOUT_MODE", "in_process")
    return FanoutService()
