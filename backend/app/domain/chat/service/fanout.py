"""채팅 이벤트 fan-out.

`settings.FANOUT_MODE`:
- `in_process`   : 단일 프로세스 메모리 dict 직배송
- `node_channel` : 다중 노드 Redis Pub/Sub (`node:{node_id}` 채널)

호출측은 모드 무관 — `fan_out_to_*` / `(un)subscribe_user_to_room` 만 사용.

WS 객체 duck typing 전제 — 핸들러가 `session_id` / `user_id` / `subscribed_rooms` 를 심는다.

`node_channel` 모드에서 publisher 는 자기 자신에게도 publish 해 `_local_*` 로 들어가는
통일 경로를 유지 (모드별 분기 최소화). 동일 채널 내 ordering 은 Redis 가 보장하므로
"subscribe → fan_out" 순서가 모든 노드에서 보존된다.

`NODE_ID`: uvicorn `--workers N` 운영 시 충돌하면 한 채널을 여러 워커가 동시 구독해
중복 수신이 발생 — 명시 지정 권장.
"""
import json
from fastapi import WebSocket, WebSocketDisconnect
from collections import defaultdict
import asyncio

from app.domain.chat.worker.node_registry import list_active_nodes
from app.core.redis import get_redis_client
from app.core.logger import get_logger
from app.core.instrumentation import (
    chat_fanout_dispatch,
    chat_fanout_publish_inc,
)
from app.core.context import request_id_var, traceparent_var
from app.core.chat.redis_key import node_channel_key, ws_route_key
from app.config.setting import settings


logger = get_logger("chat.fanout")


_SUPPORTED_MODES = ("in_process", "node_channel")


class FanoutService:
    """fan-out 인터페이스 — 모드별 분기는 본 클래스 내부에 격리.

    Singleton 으로 등록. `node_channel` 모드에서도 로컬 dict 는 유지 — 디스패처가
    envelope 을 받아 `_local_*` 로 재진입할 때 사용.
    """

    def __init__(self):
        if settings.FANOUT_MODE not in _SUPPORTED_MODES:
            raise NotImplementedError(
                f"FANOUT_MODE={settings.FANOUT_MODE!r} 미지원. "
                f"지원 모드: {_SUPPORTED_MODES}",
            )
        self._mode = settings.FANOUT_MODE
        self._room_subs: dict[str, set[WebSocket]] = defaultdict(set)
        self._user_subs: dict[str, set[WebSocket]] = defaultdict(set)
        self._local_ws_by_session: dict[str, WebSocket] = {}


    # ──────────────────── 등록 / 해제 (로컬 전용) ────────────────────
    # WS 가 이 노드에 붙어있는 것이라 cross-node 전파 불필요.

    def register_session(self, ws: WebSocket) -> None:
        """WS 연결 시 세션 등록 (방 구독은 별도).

        호출 전 핸들러가 `session_id` / `user_id` / `subscribed_rooms` 를 심어야 한다.
        """
        self._local_ws_by_session[ws.session_id] = ws
        self._user_subs[ws.user_id].add(ws)


    def register_ws_to_room(self, ws: WebSocket, room_id: str) -> None:
        """방 구독. 역매핑 `ws.subscribed_rooms` 도 갱신해 종료 시 O(1) 해제."""
        self._room_subs[room_id].add(ws)
        ws.subscribed_rooms.add(room_id)


    def unregister_ws(self, ws: WebSocket) -> None:
        """WS 종료 시 모든 dict 에서 제거. 반드시 close / Redis 정리보다 먼저 호출 —
        dispatcher 가 dead 소켓에 push 하지 않도록.
        """
        sid: str | None = getattr(ws, "session_id", None)
        uid: str | None = getattr(ws, "user_id", None)
        rooms: set[str] = getattr(ws, "subscribed_rooms", set())

        if sid is not None:
            self._local_ws_by_session.pop(sid, None)

        if uid is not None and uid in self._user_subs:
            self._user_subs[uid].discard(ws)
            if not self._user_subs[uid]:
                del self._user_subs[uid]

        for room_id in list(rooms):
            if room_id in self._room_subs:
                self._room_subs[room_id].discard(ws)
                if not self._room_subs[room_id]:
                    del self._room_subs[room_id]


    # ──────────────────── 동적 방 구독 (cross-node) ────────────────────

    async def subscribe_user_to_room(self, user_id: str, room_id: str) -> None:
        """유저의 모든 세션 (전 노드) 을 방 구독에 추가. invite / 방 생성 시 호출.

        호출 전에 RDB `chat_room_member` 와 Redis `room_members` 캐시가 먼저 갱신되어야 한다.
        오프라인 유저는 no-op. Idempotent.
        """
        if self._mode == "in_process":
            self._local_subscribe_user_to_room(user_id, room_id)
            return
        await self._publish_broadcast(
            {"op": "subscribe", "user_id": user_id, "room_id": room_id},
        )


    async def unsubscribe_user_from_room(self, user_id: str, room_id: str) -> None:
        """유저의 모든 세션 (전 노드) 을 방 구독에서 제거. leave / kick 시 호출.

        반드시 시스템 메시지 fan-out 이전에 호출:
        1) leak 차단 — send_system_message 가 실패해도 이미 구독 해제됨
        2) UX — 퇴장 당사자가 자기 퇴장 시스템 메시지를 받지 않음
        """
        if self._mode == "in_process":
            self._local_unsubscribe_user_from_room(user_id, room_id)
            return
        await self._publish_broadcast(
            {"op": "unsubscribe", "user_id": user_id, "room_id": room_id},
        )


    # ──────────────────── Fan-out (모드 분기) ────────────────────

    async def fan_out_to_room(self, room_id: str, payload: dict) -> None:
        """방의 활성 WS 전체에 브로드캐스트. `payload.sender_session_id` 가 있으면 발신자 skip."""
        if self._mode == "in_process":
            await self._local_deliver_to_room(room_id, payload)
            return
        await self._publish_broadcast(
            {"op": "room", "room_id": room_id, "payload": payload},
        )


    async def fan_out_to_user(self, user_id: str, payload: dict) -> None:
        """유저의 모든 세션에 브로드캐스트 (`room_joined` / `unread_synced` 등 user-scoped)."""
        if self._mode == "in_process":
            await self._local_deliver_to_user(user_id, payload)
            return
        await self._publish_broadcast(
            {"op": "user", "user_id": user_id, "payload": payload},
        )


    async def fan_out_to_session(self, session_id: str, payload: dict) -> None:
        """특정 세션 직송. `node_channel` 모드는 `ws_route:{sid}` 로 타깃 노드 라우팅.

        라우트가 없으면 세션 사라진 것 — silent drop.
        """
        if self._mode == "in_process":
            await self._local_deliver_to_session(session_id, payload)
            return
        await self._publish_to_session_node(session_id, payload)


    # ──────────────────── 디스패처 진입점 ────────────────────

    async def dispatch_envelope(self, envelope: dict) -> None:
        """`FanoutDispatcher` 가 Pub/Sub 메시지를 받아 호출.

        알 수 없는 op 는 warning 후 drop (구/신버전 노드 혼재 fail-open).
        publisher 가 박은 request_id / traceparent 를 contextvar 로 복원 — cross-node trace 보존.
        """
        op = envelope.get("op", "unknown")

        rid_token = request_id_var.set(envelope.get("request_id", ""))
        tp_token = traceparent_var.set(envelope.get("traceparent", ""))

        try:
            async with chat_fanout_dispatch(op):
                try:
                    if op == "room":
                        await self._local_deliver_to_room(
                            envelope["room_id"], envelope["payload"],
                        )
                    elif op == "user":
                        await self._local_deliver_to_user(
                            envelope["user_id"], envelope["payload"],
                        )
                    elif op == "session":
                        await self._local_deliver_to_session(
                            envelope["session_id"], envelope["payload"],
                        )
                    elif op == "subscribe":
                        self._local_subscribe_user_to_room(
                            envelope["user_id"], envelope["room_id"],
                        )
                    elif op == "unsubscribe":
                        self._local_unsubscribe_user_from_room(
                            envelope["user_id"], envelope["room_id"],
                        )
                    else:
                        logger.warning("알 수 없는 envelope op (drop): {}", op)
                except KeyError as e:
                    logger.warning(
                        "envelope 필드 누락 (drop): op={}, missing={}", op, e,
                    )
        finally:
            request_id_var.reset(rid_token)
            traceparent_var.reset(tp_token)


    # ──────────────────── 로컬 전달 ────────────────────

    def _local_subscribe_user_to_room(self, user_id: str, room_id: str) -> None:
        """이 노드의 user_id 세션들을 `_room_subs[room_id]` 에 추가. dead WS 는 가드로 skip."""
        for ws in list(self._user_subs.get(user_id, ())):
            sid = getattr(ws, "session_id", None)
            if sid is None or sid not in self._local_ws_by_session:
                continue
            self.register_ws_to_room(ws, room_id)


    def _local_unsubscribe_user_from_room(self, user_id: str, room_id: str) -> None:
        """이 노드의 user_id 세션들을 `_room_subs[room_id]` 에서 제거."""
        affected = list(self._user_subs.get(user_id, ()))
        if not affected:
            return

        room_set = self._room_subs.get(room_id)
        for ws in affected:
            rooms = getattr(ws, "subscribed_rooms", None)
            if rooms is not None:
                rooms.discard(room_id)
            if room_set is not None:
                room_set.discard(ws)

        if room_set is not None and not room_set:
            del self._room_subs[room_id]


    async def _local_deliver_to_room(self, room_id: str, payload: dict) -> None:
        sender_sid = payload.get("sender_session_id")
        recipients = [
            ws for ws in self._room_subs.get(room_id, ())
            if ws.session_id != sender_sid
        ]
        await self._broadcast(recipients, payload)


    async def _local_deliver_to_user(self, user_id: str, payload: dict) -> None:
        recipients = list(self._user_subs.get(user_id, ()))
        await self._broadcast(recipients, payload)


    async def _local_deliver_to_session(self, session_id: str, payload: dict) -> None:
        ws = self._local_ws_by_session.get(session_id)
        if ws is None:
            return
        await self._broadcast([ws], payload)


    # ──────────────────── publish 헬퍼 (node_channel) ────────────────────

    @staticmethod
    async def _publish_broadcast(envelope: dict) -> None:
        """활성 노드 전체 (자기 자신 포함) 에 publish.

        자기 자신에게도 publish → 디스패처가 받아 `_local_*` 로 들어가는 통일 경로 유지.
        활성 노드 0 명이면 publish skip. envelope 에 request_id/traceparent 박아 trace 보존.
        """
        nodes = await list_active_nodes()
        if not nodes:
            return

        envelope.setdefault("request_id", request_id_var.get())
        envelope.setdefault("traceparent", traceparent_var.get())

        chat_fanout_publish_inc(envelope.get("op", "unknown"))

        redis = await get_redis_client()
        envelope_json = json.dumps(envelope)
        pipe = redis.pipeline(transaction=False)
        for node_id in nodes:
            pipe.publish(node_channel_key(node_id), envelope_json)
        await pipe.execute()


    @staticmethod
    async def _publish_to_session_node(session_id: str, payload: dict) -> None:
        """특정 세션이 붙은 노드에만 publish. 라우트가 없으면 세션 만료 — silent drop."""
        redis = await get_redis_client()
        target_node = await redis.get(ws_route_key(session_id))
        if target_node is None:
            return

        envelope = {
            "op": "session",
            "session_id": session_id,
            "payload": payload,
            "request_id": request_id_var.get(),
            "traceparent": traceparent_var.get(),
        }
        chat_fanout_publish_inc("session")
        await redis.publish(node_channel_key(target_node), json.dumps(envelope))


    async def _broadcast(self, recipients: list[WebSocket], payload: dict) -> None:
        """여러 WS 에 동시 push — `gather(return_exceptions=True)` 로 한 WS 실패 격리.

        dead 세션 (RuntimeError / WebSocketDisconnect) 은 즉시 unregister — 좀비 세션에
        반복 시도되는 워닝 폭발 차단. 그 외 예외는 일시적일 수 있어 정리하지 않고 로그만.
        """
        if not recipients:
            return
        results = await asyncio.gather(
            *(ws.send_json(payload) for ws in recipients),
            return_exceptions=True,
        )
        for ws, result in zip(recipients, results):
            if not isinstance(result, Exception):
                continue
            logger.warning(
                "fan-out send 실패: session_id={}, err={!r}",
                getattr(ws, "session_id", "?"),
                result,
            )
            if isinstance(result, (RuntimeError, WebSocketDisconnect)):
                self.unregister_ws(ws)
