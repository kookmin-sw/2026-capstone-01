"""채팅 방 응답 스키마 회귀 테스트.

`LastMessagePreviewResponse.content` 는 메시지 type 별로 다른 모양을 받는다
(text=str / image·file=dict / system=object / 삭제됨=null).

과거에는 `Optional[str]` 로 좁혀져 있어 system 메시지가 last_message 인 방 리스트
응답이 Pydantic 직렬화 단계에서 500 으로 터지는 버그가 있었다. 같은 회귀가 다시
발생하지 않도록 스키마 단위에서 다형 입력을 직접 검증한다.
"""
import pytest
from datetime import datetime, timezone

from app.domain.chat.schema.room import LastMessagePreviewResponse


NOW = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)


def _build(content):
    return LastMessagePreviewResponse(
        message_id="MSG_1",
        server_seq=1,
        sender_id=None,
        type="system",
        content=content,
        created_at=NOW,
    )


@pytest.mark.unit
class TestLastMessagePreviewResponseContent:
    """`content` 는 string / object / null 를 모두 받아야 한다."""

    def test_accepts_text_string(self):
        resp = _build("hello")
        assert resp.content == "hello"


    def test_accepts_system_created_dict(self):
        """system.created — `{action, actor_id}`."""
        payload = {"action": "created", "actor_id": "U_A"}
        resp = _build(payload)
        assert resp.content == payload


    def test_accepts_system_join_dict_with_target_ids(self):
        """system.join — `target_ids` 까지 보존."""
        payload = {"action": "join", "actor_id": "U_A", "target_ids": ["U_B", "U_C"]}
        resp = _build(payload)
        assert resp.content == payload


    def test_accepts_image_dict(self):
        payload = {"url": "https://cdn.example.com/p.jpg", "name": "p.jpg"}
        resp = _build(payload)
        assert resp.content == payload


    def test_accepts_null_for_deleted_message(self):
        resp = _build(None)
        assert resp.content is None


    def test_dict_content_serializes_as_object_not_string(self):
        """JSON 직렬화 시 dict 가 그대로 객체로 내려가야 함.

        만약 `content` 가 `str` 로 좁혀져 있으면 dict 입력 자체가 ValidationError 로
        터지거나, str 강제 변환되어 `"{...}"` 형태가 되므로 이 단언이 깨진다.
        """
        payload = {"action": "kick", "actor_id": "U_A", "target_ids": ["U_X"]}
        resp = _build(payload)
        dumped = resp.model_dump()
        assert isinstance(dumped["content"], dict)
        assert dumped["content"] == payload
