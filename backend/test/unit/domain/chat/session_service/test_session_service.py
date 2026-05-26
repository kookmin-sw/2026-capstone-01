"""SessionService 단위 테스트 — Redis 명령 시퀀스 + 한도 초과 revoke."""
from unittest.mock import AsyncMock
import pytest

from app.core.chat.redis_key import (
    MAX_SESSIONS_PER_USER,
    sess_key,
    sessions_key,
    ws_route_key,
)


# ──────────────────────────────────────────────────────────────────
# create_session
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestCreateSession:
    async def test_issues_ws_prefixed_session_id(self, service):
        sid = await service.create_session(user_id="U_A", token_jti="jti_1")
        assert sid.startswith("WS_")


    async def test_first_pipeline_writes_four_keys(self, service, redis_mock):
        """create_session 의 첫 pipeline 에서 HSET + EXPIRE + ZADD + SET 4개 write."""
        await service.create_session(user_id="U_A", token_jti="jti_1")

        assert len(redis_mock._pipes) >= 1
        p0 = redis_mock._pipes[0]
        assert p0.hset.called
        assert p0.expire.called
        assert p0.zadd.called
        assert p0.set.called
        p0.execute.assert_awaited()


    async def test_limit_enforced_revokes_oldest(self, service, redis_mock, fanout_mock):
        """한도 초과 시 가장 오래된 세션에 session_revoked 직송 + DEL."""
        redis_mock.zcard = AsyncMock(side_effect=[MAX_SESSIONS_PER_USER + 1, MAX_SESSIONS_PER_USER])
        redis_mock.zrange = AsyncMock(side_effect=[["WS_old"]])

        await service.create_session(user_id="U_A", token_jti="jti_1")

        fanout_mock.fan_out_to_session.assert_awaited_once()
        args, _ = fanout_mock.fan_out_to_session.call_args
        assert args[0] == "WS_old"
        assert args[1] == {"type": "session_revoked", "session_id": "WS_old"}

        # revoke pipeline 에서 sessions ZREM + sess/ws_route DEL
        revoke_pipes = [p for p in redis_mock._pipes if p.zrem.called and p.delete.called]
        assert revoke_pipes, "revoke pipeline 을 찾지 못함"


# ──────────────────────────────────────────────────────────────────
# heartbeat
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestHeartbeat:
    async def test_extends_three_keys_with_zadd_xx(self, service, redis_mock):
        await service.heartbeat(session_id="WS_1", user_id="U_A")

        assert len(redis_mock._pipes) == 1
        p = redis_mock._pipes[0]

        # expire 는 sess + ws_route 두 번
        expire_keys = [c.args[0] for c in p.expire.call_args_list]
        assert sess_key("WS_1") in expire_keys
        assert ws_route_key("WS_1") in expire_keys

        # zadd XX 옵션으로 기존 멤버 score 만 갱신
        p.zadd.assert_called_once()
        assert p.zadd.call_args.kwargs.get("xx") is True


# ──────────────────────────────────────────────────────────────────
# session_exists / get_user_id / update_token_jti
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSimpleAccessors:
    async def test_session_exists_true_when_key_present(self, service, redis_mock):
        redis_mock.exists = AsyncMock(return_value=1)
        assert await service.session_exists("WS_1") is True


    async def test_session_exists_false_when_key_absent(self, service, redis_mock):
        redis_mock.exists = AsyncMock(return_value=0)
        assert await service.session_exists("WS_1") is False


    async def test_get_user_id_returns_value(self, service, redis_mock):
        redis_mock.hget = AsyncMock(return_value="U_A")
        assert await service.get_user_id("WS_1") == "U_A"


    async def test_get_user_id_returns_none_when_missing(self, service, redis_mock):
        redis_mock.hget = AsyncMock(return_value=None)
        assert await service.get_user_id("WS_ghost") is None


    async def test_update_token_jti_writes_hash_field(self, service, redis_mock):
        await service.update_token_jti("WS_1", "new_jti")

        redis_mock.hset.assert_awaited_once()
        args, _ = redis_mock.hset.call_args
        assert args == (sess_key("WS_1"), "token_jti", "new_jti")


# ──────────────────────────────────────────────────────────────────
# terminate_session
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestTerminate:
    async def test_deletes_sess_ws_route_and_zrem_sessions(self, service, redis_mock):
        await service.terminate_session("WS_1", "U_A")

        assert len(redis_mock._pipes) == 1
        p = redis_mock._pipes[0]

        # delete 는 sess + ws_route 두 키
        delete_keys = [c.args[0] for c in p.delete.call_args_list]
        assert sess_key("WS_1") in delete_keys
        assert ws_route_key("WS_1") in delete_keys

        # zrem 은 sessions 에서 session_id 제거
        p.zrem.assert_called_once_with(sessions_key("U_A"), "WS_1")


# ──────────────────────────────────────────────────────────────────
# revoke_all_sessions — 회원 탈퇴 등 전수 강제 종료
# ──────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRevokeAllSessions:
    """Tests for SessionService.revoke_all_sessions."""

    async def test_returns_zero_when_user_has_no_active_sessions(
        self, service, redis_mock, fanout_mock,
    ):
        """오프라인 유저 — 빈 ZSET → 0 반환, 부수효과 없음."""
        redis_mock.zrange = AsyncMock(return_value=[])

        count = await service.revoke_all_sessions(user_id="U_A")

        assert count == 0
        fanout_mock.fan_out_to_session.assert_not_awaited()
        # pipeline 도 호출 안 됨 (early return)
        for p in redis_mock._pipes:
            assert not p.delete.called


    async def test_emits_session_revoked_event_for_each_session(
        self, service, redis_mock, fanout_mock,
    ):
        """각 세션마다 session_revoked 이벤트 직송. node_channel 모드에선 ws_route 라우팅."""
        redis_mock.zrange = AsyncMock(return_value=["WS_1", "WS_2", "WS_3"])

        count = await service.revoke_all_sessions(user_id="U_A")

        assert count == 3
        assert fanout_mock.fan_out_to_session.await_count == 3
        for idx, c in enumerate(fanout_mock.fan_out_to_session.call_args_list):
            sid = f"WS_{idx + 1}"
            assert c.args[0] == sid
            assert c.args[1] == {"type": "session_revoked", "session_id": sid}


    async def test_pipeline_deletes_sess_ws_route_and_sessions_zset(
        self, service, redis_mock,
    ):
        """한 pipeline 안에서 모든 sess: / ws_route: + sessions:{uid} 통째로 DEL."""
        redis_mock.zrange = AsyncMock(return_value=["WS_1", "WS_2"])

        await service.revoke_all_sessions(user_id="U_A")

        # 마지막 pipeline 이 revoke 처리 — fanout 호출 뒤
        revoke_pipe = redis_mock._pipes[-1]
        revoke_pipe.execute.assert_awaited()

        # delete 인자 모음 — 단일 DEL 에 (sess, ws_route) 2개 묶이는 케이스 + sessions DEL
        all_delete_args = [
            arg for c in revoke_pipe.delete.call_args_list for arg in c.args
        ]
        assert sess_key("WS_1") in all_delete_args
        assert sess_key("WS_2") in all_delete_args
        assert ws_route_key("WS_1") in all_delete_args
        assert ws_route_key("WS_2") in all_delete_args
        assert sessions_key("U_A") in all_delete_args
