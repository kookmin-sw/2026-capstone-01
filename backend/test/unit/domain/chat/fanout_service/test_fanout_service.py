"""FanoutService 단위 테스트 — in-process dict fan-out 의 핵심 동작 검증."""
from unittest.mock import AsyncMock, MagicMock
from test.unit.domain.chat.fanout_service.conftest import make_ws
import pytest
import json


# ──────────────────────────────────────────────────────────────────
# 등록 / 해제
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRegister:
    def test_register_session_adds_to_user_subs(self, fanout):
        ws = make_ws("WS_1", "U_A")
        fanout.register_session(ws)

        assert ws in fanout._user_subs["U_A"]
        assert fanout._local_ws_by_session["WS_1"] is ws


    def test_register_ws_to_room_adds_to_room_subs_and_back_index(self, fanout):
        ws = make_ws("WS_1", "U_A")
        fanout.register_ws_to_room(ws, "CR_1")

        assert ws in fanout._room_subs["CR_1"]
        assert "CR_1" in ws.subscribed_rooms  # 역매핑


@pytest.mark.unit
class TestUnregister:
    def test_unregister_clears_all_dicts(self, fanout):
        ws_a = make_ws("WS_a", "U_A")
        ws_b = make_ws("WS_b", "U_B")

        fanout.register_session(ws_a)
        fanout.register_session(ws_b)
        fanout.register_ws_to_room(ws_a, "CR_1")
        fanout.register_ws_to_room(ws_b, "CR_1")
        fanout.register_ws_to_room(ws_a, "CR_2")

        fanout.unregister_ws(ws_a)

        # WS_a 는 완전히 제거, WS_b 는 유지
        assert "WS_a" not in fanout._local_ws_by_session
        assert "WS_b" in fanout._local_ws_by_session
        assert "U_A" not in fanout._user_subs  # 빈 set → key 제거
        assert ws_b in fanout._user_subs["U_B"]
        assert ws_a not in fanout._room_subs["CR_1"]
        assert ws_b in fanout._room_subs["CR_1"]
        assert "CR_2" not in fanout._room_subs  # 혼자 있던 방은 key 까지 제거


    def test_unregister_tolerates_missing_attributes(self, fanout):
        """속성이 없는 WS 라도 예외 없이 지나가야 한다 (방어적)."""
        ws = make_ws("WS_1", "U_A")
        # subscribed_rooms 를 의도적으로 지워서 방어 확인
        del ws.subscribed_rooms
        fanout.register_session(ws)
        # 예외 없이 통과
        fanout.unregister_ws(ws)

        assert "WS_1" not in fanout._local_ws_by_session


# ──────────────────────────────────────────────────────────────────
# fan_out_to_room
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestFanOutToRoom:
    async def test_skips_sender_session(self, fanout):
        """발신 세션은 skip, 다른 세션 (같은 유저 다른 세션 / 다른 유저) 는 수신."""
        phone = make_ws("WS_phone", "U_A")
        pc = make_ws("WS_pc", "U_A")
        bob = make_ws("WS_bob", "U_B")
        for ws in (phone, pc, bob):
            fanout.register_session(ws)
            fanout.register_ws_to_room(ws, "CR_1")

        await fanout.fan_out_to_room(
            "CR_1",
            {"type": "message.new", "sender_session_id": "WS_phone"},
        )

        phone.send_json.assert_not_called()       # 발신자 skip
        pc.send_json.assert_awaited_once()         # 같은 유저 다른 세션
        bob.send_json.assert_awaited_once()        # 다른 유저


    async def test_no_recipients_noop(self, fanout):
        """빈 방에 발행해도 예외 없이 통과."""
        await fanout.fan_out_to_room("CR_empty", {"type": "message.new", "sender_session_id": "?"})


    async def test_missing_sender_session_id_delivers_to_all(self, fanout):
        """payload 에 sender_session_id 없으면 전원에게 전달 (시스템 메시지 등의 경우)."""
        a = make_ws("WS_a", "U_A")
        b = make_ws("WS_b", "U_B")
        for ws in (a, b):
            fanout.register_session(ws)
            fanout.register_ws_to_room(ws, "CR_1")

        await fanout.fan_out_to_room("CR_1", {"type": "system"})

        a.send_json.assert_awaited_once()
        b.send_json.assert_awaited_once()


# ──────────────────────────────────────────────────────────────────
# fan_out_to_user / fan_out_to_session
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestFanOutToUser:
    async def test_delivers_to_all_user_sessions(self, fanout):
        phone = make_ws("WS_phone", "U_A")
        pc = make_ws("WS_pc", "U_A")
        bob = make_ws("WS_bob", "U_B")
        for ws in (phone, pc, bob):
            fanout.register_session(ws)

        await fanout.fan_out_to_user("U_A", {"type": "room_joined", "room_id": "CR_1"})

        phone.send_json.assert_awaited_once()
        pc.send_json.assert_awaited_once()
        bob.send_json.assert_not_called()


    async def test_no_sessions_noop(self, fanout):
        await fanout.fan_out_to_user("U_ghost", {"type": "room_joined", "room_id": "?"})


@pytest.mark.unit
class TestFanOutToSession:
    async def test_delivers_to_target_only(self, fanout):
        phone = make_ws("WS_phone", "U_A")
        pc = make_ws("WS_pc", "U_A")
        for ws in (phone, pc):
            fanout.register_session(ws)

        await fanout.fan_out_to_session("WS_phone", {"type": "session_revoked", "session_id": "WS_phone"})

        phone.send_json.assert_awaited_once()
        pc.send_json.assert_not_called()


    async def test_missing_session_silent(self, fanout):
        """이미 close 된 세션은 dict 에서 pop 된 상태 — 조용히 무시."""
        await fanout.fan_out_to_session("WS_ghost", {"type": "session_revoked", "session_id": "?"})


# ──────────────────────────────────────────────────────────────────
# 에러 허용 / FANOUT_MODE 가드
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestErrorTolerance:
    async def test_one_ws_failure_does_not_block_others(self, fanout):
        """한 WS 가 send 실패해도 다른 WS 는 영향 없이 수신."""
        ok = make_ws("WS_ok", "U_A")
        boom = make_ws("WS_boom", "U_B")
        boom.send_json.side_effect = RuntimeError("connection closed")
        for ws in (ok, boom):
            fanout.register_session(ws)
            fanout.register_ws_to_room(ws, "CR_1")

        # 예외 새지 않고 통과
        await fanout.fan_out_to_room("CR_1", {"type": "system"})
        ok.send_json.assert_awaited_once()


@pytest.mark.unit
class TestFanoutModeGuard:
    def test_unsupported_mode_raises(self, monkeypatch):
        """미지원 모드로 잘못 기동하면 생성자에서 NotImplementedError.

        지원 모드(`in_process` / `node_channel`) 외 값을 env 로 흘려보낸 경우 — 오타 등.
        """
        from app.config import setting as setting_module
        monkeypatch.setattr(setting_module.settings, "FANOUT_MODE", "broken_mode")

        from app.domain.chat.service.fanout import FanoutService
        with pytest.raises(NotImplementedError, match="미지원"):
            FanoutService()


    def test_node_channel_mode_initializes(self, monkeypatch):
        """`node_channel` 모드로 부팅하면 생성자 통과 (디스패처/레지스트리 와이어링은 lifespan 책임)."""
        from app.config import setting as setting_module
        monkeypatch.setattr(setting_module.settings, "FANOUT_MODE", "node_channel")

        from app.domain.chat.service.fanout import FanoutService
        svc = FanoutService()
        # 로컬 dict 들은 두 모드에서 동일하게 사용됨 — dispatcher 가 받아 채워주는 진입점.
        assert svc._mode == "node_channel"
        assert svc._room_subs == {}
        assert svc._user_subs == {}
        assert svc._local_ws_by_session == {}


# ──────────────────────────────────────────────────────────────────
# node_channel 모드 — publish 위임 (dispatch_envelope 진입 시 _local_* 호출 검증)
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestNodeChannelDispatch:
    """`node_channel` 모드에서 디스패처가 받은 envelope 이 로컬 전달 경로로 들어가는지 검증.

    publish 자체는 Redis 의존이라 mock 으로 격리된 별도 통합 테스트에서 다루고, 여기선
    `dispatch_envelope` 가 모드 무관 로컬 dict 를 정확히 구동하는지에 집중.
    """

    @pytest.fixture
    def node_fanout(self, monkeypatch):
        from app.config import setting as setting_module
        monkeypatch.setattr(setting_module.settings, "FANOUT_MODE", "node_channel")
        from app.domain.chat.service.fanout import FanoutService
        return FanoutService()


    async def test_dispatch_room_envelope_delivers_locally(self, node_fanout):
        ws = make_ws("WS_a", "U_A")
        node_fanout.register_session(ws)
        node_fanout.register_ws_to_room(ws, "CR_1")

        await node_fanout.dispatch_envelope({
            "op": "room",
            "room_id": "CR_1",
            "payload": {"type": "message.new", "sender_session_id": "WS_other"},
        })

        ws.send_json.assert_awaited_once()


    async def test_dispatch_user_envelope_delivers_to_all_user_sessions(self, node_fanout):
        phone = make_ws("WS_phone", "U_A")
        pc = make_ws("WS_pc", "U_A")
        for ws in (phone, pc):
            node_fanout.register_session(ws)

        await node_fanout.dispatch_envelope({
            "op": "user",
            "user_id": "U_A",
            "payload": {"type": "room_joined", "room_id": "CR_1"},
        })

        phone.send_json.assert_awaited_once()
        pc.send_json.assert_awaited_once()


    async def test_dispatch_session_envelope_delivers_to_target_only(self, node_fanout):
        a = make_ws("WS_a", "U_A")
        b = make_ws("WS_b", "U_B")
        for ws in (a, b):
            node_fanout.register_session(ws)

        await node_fanout.dispatch_envelope({
            "op": "session",
            "session_id": "WS_a",
            "payload": {"type": "session_revoked", "session_id": "WS_a"},
        })

        a.send_json.assert_awaited_once()
        b.send_json.assert_not_called()


    async def test_dispatch_subscribe_envelope_adds_local_user_to_room(self, node_fanout):
        ws = make_ws("WS_a", "U_A")
        node_fanout.register_session(ws)

        await node_fanout.dispatch_envelope({
            "op": "subscribe", "user_id": "U_A", "room_id": "CR_new",
        })

        assert ws in node_fanout._room_subs["CR_new"]
        assert "CR_new" in ws.subscribed_rooms


    async def test_dispatch_unsubscribe_envelope_removes_local_user_from_room(self, node_fanout):
        ws = make_ws("WS_a", "U_A")
        node_fanout.register_session(ws)
        node_fanout.register_ws_to_room(ws, "CR_1")

        await node_fanout.dispatch_envelope({
            "op": "unsubscribe", "user_id": "U_A", "room_id": "CR_1",
        })

        assert "CR_1" not in node_fanout._room_subs   # 마지막 구독자 빠지면 키 정리
        assert "CR_1" not in ws.subscribed_rooms


    async def test_dispatch_unknown_op_drops_silently(self, node_fanout):
        # 미래 버전이 새 op 를 추가했고 본 노드가 구버전인 경우 — 다운되지 않고 drop.
        await node_fanout.dispatch_envelope({"op": "future_op", "data": 1})


    async def test_dispatch_envelope_missing_field_drops_silently(self, node_fanout):
        # payload 누락 등 손상된 envelope 도 drop.
        await node_fanout.dispatch_envelope({"op": "room", "room_id": "CR_1"})


# ──────────────────────────────────────────────────────────────────
# node_channel 모드 — publish 경로 (Redis publish + envelope 정확성)
# ──────────────────────────────────────────────────────────────────


def _make_redis_mock_for_publish() -> MagicMock:
    """publish pipeline 호출을 캡처하는 redis mock.

    `pipe.publish` 인자를 자기 list 에 모아 두면 테스트가 envelope payload 까지 검증 가능.
    `pipe.execute` / `redis.publish` / `redis.get` 모두 AsyncMock 으로 await 가능.
    """
    pipe = MagicMock(name="pipe")
    pipe.published: list[tuple[str, str]] = []

    def _publish(channel: str, payload: str):
        pipe.published.append((channel, payload))
        return pipe
    pipe.publish = MagicMock(side_effect=_publish)
    pipe.execute = AsyncMock()

    redis = MagicMock(name="redis")
    redis.pipeline = MagicMock(return_value=pipe)
    redis.publish = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis._pipe = pipe   # 테스트 접근용
    return redis


@pytest.fixture
def node_channel_env(monkeypatch):
    """`node_channel` 모드 + redis mock + list_active_nodes mock 셋업.

    반환: `(fanout, redis_mock, set_active_nodes)` 튜플.
    `set_active_nodes(node_ids)` 로 활성 노드 리스트 동적 변경 가능.
    """
    from app.config import setting as setting_module
    monkeypatch.setattr(setting_module.settings, "FANOUT_MODE", "node_channel")

    redis_mock = _make_redis_mock_for_publish()

    async def _get_client():
        return redis_mock
    monkeypatch.setattr(
        "app.domain.chat.service.fanout.get_redis_client", _get_client,
    )

    active: list[str] = []

    async def _list_active_nodes():
        return list(active)
    monkeypatch.setattr(
        "app.domain.chat.service.fanout.list_active_nodes", _list_active_nodes,
    )

    def set_active_nodes(node_ids: list[str]) -> None:
        active.clear()
        active.extend(node_ids)

    from app.domain.chat.service.fanout import FanoutService
    return FanoutService(), redis_mock, set_active_nodes


@pytest.mark.unit
class TestNodeChannelPublish:
    """`node_channel` 모드의 publisher 경로 — envelope 직렬화 + 채널 라우팅 검증."""

    async def test_fan_out_to_room_publishes_to_all_active_nodes(
        self, node_channel_env,
    ):
        fanout, redis_mock, set_active_nodes = node_channel_env
        set_active_nodes(["node-A", "node-B"])

        await fanout.fan_out_to_room("CR_1", {"type": "message.new", "sender_session_id": "S1"})

        assert len(redis_mock._pipe.published) == 2
        channels = [c for c, _ in redis_mock._pipe.published]
        assert channels == ["node:node-A", "node:node-B"]
        envelope = json.loads(redis_mock._pipe.published[0][1])
        assert envelope == {
            "op": "room",
            "room_id": "CR_1",
            "payload": {"type": "message.new", "sender_session_id": "S1"},
            "request_id": "",
            "traceparent": "",
        }
        redis_mock._pipe.execute.assert_awaited_once()


    async def test_fan_out_skips_publish_when_no_active_nodes(
        self, node_channel_env,
    ):
        """startup race 직후 / 전체 shutdown 직후 — 빈 노드 리스트면 publish 자체 skip."""
        fanout, redis_mock, set_active_nodes = node_channel_env
        set_active_nodes([])

        await fanout.fan_out_to_room("CR_1", {"type": "system"})

        redis_mock.pipeline.assert_not_called()


    async def test_fan_out_to_user_publishes_user_envelope(self, node_channel_env):
        fanout, redis_mock, set_active_nodes = node_channel_env
        set_active_nodes(["node-A"])

        await fanout.fan_out_to_user("U_A", {"type": "room_joined", "room_id": "CR_1"})

        envelope = json.loads(redis_mock._pipe.published[0][1])
        assert envelope == {
            "op": "user",
            "user_id": "U_A",
            "payload": {"type": "room_joined", "room_id": "CR_1"},
            "request_id": "",
            "traceparent": "",
        }


    async def test_subscribe_publishes_subscribe_envelope(self, node_channel_env):
        """control-plane subscribe 도 동일 broadcast 경로로 모든 노드에 전파."""
        fanout, redis_mock, set_active_nodes = node_channel_env
        set_active_nodes(["node-A", "node-B"])

        await fanout.subscribe_user_to_room("U_A", "CR_new")

        assert len(redis_mock._pipe.published) == 2
        envelope = json.loads(redis_mock._pipe.published[0][1])
        assert envelope == {
            "op": "subscribe", "user_id": "U_A", "room_id": "CR_new",
            "request_id": "", "traceparent": "",
        }


    async def test_unsubscribe_publishes_unsubscribe_envelope(self, node_channel_env):
        fanout, redis_mock, set_active_nodes = node_channel_env
        set_active_nodes(["node-A"])

        await fanout.unsubscribe_user_from_room("U_A", "CR_1")

        envelope = json.loads(redis_mock._pipe.published[0][1])
        assert envelope == {
            "op": "unsubscribe", "user_id": "U_A", "room_id": "CR_1",
            "request_id": "", "traceparent": "",
        }


    async def test_fan_out_to_session_publishes_to_target_node_only(
        self, node_channel_env,
    ):
        """`ws_route:{sid}` 룩업 → 타깃 노드 1곳만 publish (broadcast 낭비 차단)."""
        fanout, redis_mock, set_active_nodes = node_channel_env
        set_active_nodes(["node-A", "node-B", "node-C"])  # 활성 다수
        redis_mock.get = AsyncMock(return_value="node-B")

        await fanout.fan_out_to_session("SESS_x", {"type": "session_revoked", "session_id": "SESS_x"})

        # broadcast pipe 가 아니라 단일 publish 만 호출
        redis_mock.pipeline.assert_not_called()
        redis_mock.publish.assert_awaited_once()
        channel, payload = redis_mock.publish.await_args.args
        assert channel == "node:node-B"
        envelope = json.loads(payload)
        assert envelope == {
            "op": "session",
            "session_id": "SESS_x",
            "payload": {"type": "session_revoked", "session_id": "SESS_x"},
            "request_id": "",
            "traceparent": "",
        }


    async def test_fan_out_to_session_drops_when_route_missing(
        self, node_channel_env,
    ):
        """세션이 이미 종료돼 `ws_route` 가 없으면 publish 자체 skip — silent drop."""
        fanout, redis_mock, _ = node_channel_env
        redis_mock.get = AsyncMock(return_value=None)

        await fanout.fan_out_to_session("SESS_dead", {"type": "session_revoked", "session_id": "SESS_dead"})

        redis_mock.publish.assert_not_called()
