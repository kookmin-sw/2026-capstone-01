"""채팅 이벤트 fan-out.

두 가지 동작 모드 — `settings.FANOUT_MODE` 로 결정:
    - `in_process`   : 단일 프로세스 메모리 dict 직배송 (개발 / 단일 노드).
    - `node_channel` : 다중 노드 Redis Pub/Sub. `node:{node_id}` 채널 모델.
                       각 노드가 자기 채널만 구독하고, publisher 는 활성 노드
                       전체에 broadcast 또는 `ws_route:{sid}` 로 단일 노드 라우팅.

`FanoutService` 는 모드와 무관한 인터페이스 (`fan_out_to_*` / `subscribe_user_to_room` /
`unsubscribe_user_from_room`) 를 제공해 호출측 (RoomService / MessageService /
SessionService) 코드는 모드 전환에 영향받지 않는다.

**WS 객체 전제 (duck typing)**:
    - `ws.session_id: str`
    - `ws.user_id: str`
    - `ws.subscribed_rooms: set[str]`
연결 핸들러(`chat_ws_router`) 가 `WebSocket` 인스턴스에 이 세 속성을 심어두고
`register_session` + `register_ws_to_room` 을 호출한다.

**채널 envelope** (JSON, `node_channel` 모드):
    {"op": "room",        "room_id": "...",    "payload": {...}}
    {"op": "user",        "user_id": "...",    "payload": {...}}
    {"op": "session",     "session_id": "...", "payload": {...}}
    {"op": "subscribe",   "user_id": "...",    "room_id": "..."}
    {"op": "unsubscribe", "user_id": "...",    "room_id": "..."}

publisher 는 자기 자신의 채널에도 publish 한다 — 디스패처가 받아 `_local_*` 로 들어가는
**통일 경로** 를 유지해 모드별 분기 로직을 최소화. 추가 latency 는 Redis 단일 round-trip
수준이라 chat 도메인에선 무시 가능.

ordering 보장: 동일 채널 내 메시지는 publish 순서대로 전달되므로 "subscribe → fan_out"
순서가 모든 노드에서 보존된다 (room.py 의 race 차단 의도가 그대로 유지됨).

`NODE_ID` 주의: 멀티 워커(uvicorn `--workers N`)로 같은 호스트에서 여러 프로세스를
띄우면 기본값(hostname)이 충돌해 한 채널을 여러 워커가 동시 구독한다. 정상 동작은 하지만
중복 수신으로 인한 효율 손실이 있으므로 멀티 워커 운영 시 `NODE_ID` env 를 명시 지정 권장.
"""
import json
from fastapi import WebSocket, WebSocketDisconnect
from collections import defaultdict
import asyncio

from app.domain.chat.worker.node_registry import list_active_nodes
from app.config.setting import settings
from app.core.chat.redis_key import node_channel_key, ws_route_key
from app.core.context import request_id_var, traceparent_var
from app.core.instrumentation import (
    chat_fanout_dispatch,
    chat_fanout_publish_inc,
)
from app.core.logger import get_logger
from app.core.redis import get_redis_client


logger = get_logger("chat.fanout")


# 지원되는 동작 모드 — 추가 시 `_validate_mode` 만 손대도록 모듈 상수로 분리.
_SUPPORTED_MODES = ("in_process", "node_channel")


class FanoutService:
    """fan-out 인터페이스. 모드별 분기는 본 클래스 내부에 격리.

    Singleton 으로 Container 에 등록되어 프로세스 전체가 동일한 dict 를 공유한다.
    `node_channel` 모드에서도 dict 는 **로컬 전달용** 으로 유지 — 디스패처가 Redis 에서
    envelope 를 받아 `_local_*` 로 다시 진입할 때 사용된다.
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
    # 이 세 메서드는 항상 로컬 dict 만 갱신 — WS 자체가 이 노드에 붙어있는 것이므로
    # cross-node 전파가 불필요하다.

    def register_session(self, ws: WebSocket) -> None:
        """WS 연결 시 세션 단위 등록 (방 구독은 별도).

        호출 전 핸들러가 반드시 `ws.session_id` / `ws.user_id` / `ws.subscribed_rooms`
        속성을 심어둬야 한다.
        """
        self._local_ws_by_session[ws.session_id] = ws
        self._user_subs[ws.user_id].add(ws)


    def register_ws_to_room(self, ws: WebSocket, room_id: str) -> None:
        """방 구독. 역매핑(`ws.subscribed_rooms`) 을 함께 갱신해 종료 시 O(1) 해제."""
        self._room_subs[room_id].add(ws)
        ws.subscribed_rooms.add(room_id)


    def unregister_ws(self, ws: WebSocket) -> None:
        """WS 종료 시 모든 dict 에서 제거.

        **반드시 `ws.close()` 또는 Redis 정리보다 먼저** 호출되어야 dispatcher 가
        이미 close 된 소켓에 push 하지 않는다. 빈 set 은 함께 pop 해
        메모리 누수 방지.
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
        """유저의 모든 세션 (전 노드 포함) 을 방 구독에 추가. invite / 방 생성 시 호출.

        WS 가 처음 연결될 때 (`ws.py` 의 `list_user_room_ids` 경로) 구독되는 정적
        등록과 짝을 이루는 동적 등록 — 그 이후 새로 가입한 방에 대해 호출. 호출 전에
        RDB `chat_room_member` 와 Redis `room_members` 캐시가 먼저 갱신되어야 한다
        (시스템 메시지 fan-out 이전에 구독되어야 자기 초대된 메시지 수신).

        오프라인 유저는 모든 노드의 `_user_subs.get(user_id, ())` 가 빈 set 이라 no-op —
        다음 WS 연결 시 정적 등록 경로로 자연스럽게 채워진다.

        Idempotent — `set.add` 로 중복 호출 안전.
        """
        if self._mode == "in_process":
            self._local_subscribe_user_to_room(user_id, room_id)
            return
        await self._publish_broadcast(
            {"op": "subscribe", "user_id": user_id, "room_id": room_id},
        )


    async def unsubscribe_user_from_room(self, user_id: str, room_id: str) -> None:
        """유저의 모든 세션 (전 노드 포함) 을 방 구독에서 제거. leave / kick 시 호출.

        반드시 leave/kick 의 시스템 메시지 (`fan_out_to_room`) **이전** 에 호출 —
        1) leak 차단 보장: send_system_message 가 실패해도 이미 구독 해제됨
        2) UX: 퇴장 당사자는 `room_left` 이벤트만 받고 자기 퇴장 시스템 메시지는 수신 안 함
            (카톡/슬랙/디스코드 표준 동작)
        Redis `room_members` SREM 은 송신 경로 (`_ensure_membership`) 차단용으로
        먼저 처리되며, 이 메서드는 수신 경로 (`_room_subs`) 차단용으로 별도 동작.

        오프라인 유저는 모든 노드 빈 set 이라 no-op.
        """
        if self._mode == "in_process":
            self._local_unsubscribe_user_from_room(user_id, room_id)
            return
        await self._publish_broadcast(
            {"op": "unsubscribe", "user_id": user_id, "room_id": room_id},
        )


    # ──────────────────── Fan-out (모드 분기) ────────────────────

    async def fan_out_to_room(self, room_id: str, payload: dict) -> None:
        """방의 활성 WS 전체에 브로드캐스트. 발신 세션은 서버에서 skip.

        `sender_session_id` 필드가 payload 에 있어야 발신자 본인의 WS 가 자기 메시지를
        중복 수신하지 않는다. message.new / message.updated / read / 시스템 메시지 등
        room-scoped 이벤트 공용.

        `node_channel` 모드: 활성 전 노드의 `node:{node_id}` 채널에 publish. 각 노드의
        디스패처가 자기 `_room_subs` 로 로컬 전달.
        """
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
        """특정 세션 직송 (`session_revoked` / 메시지 ACK 등 session-scoped).

        `node_channel` 모드: `ws_route:{sid}` 로 타깃 노드를 조회해 단일 노드 채널에만
        publish. 라우트가 비어있으면 (TTL 만료 / terminate_session 후) 세션 사라진 것이라
        조용히 무시 — `in_process` 모드의 silent drop 과 동일 의미.
        """
        if self._mode == "in_process":
            await self._local_deliver_to_session(session_id, payload)
            return
        await self._publish_to_session_node(session_id, payload)


    # ──────────────────── 디스패처 진입점 ────────────────────

    async def dispatch_envelope(self, envelope: dict) -> None:
        """`FanoutDispatcher` 가 Redis Pub/Sub 메시지를 수신해 호출.

        envelope 의 `op` 별로 `_local_*` 로 라우팅. 알 수 없는 op 는 warning 후 drop —
        구버전/신버전 노드 혼재 시에도 다운되지 않도록 fail-open.

        cross-node trace 보존 — publisher 가 박은 request_id / traceparent 를 contextvar
        로 복원해 본 노드의 로그 / 향후 OTel span 에서 동일 ID 가 보이도록 한다.
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


    # ──────────────────── 로컬 전달 (in-process / 디스패처 진입) ────────────────────

    def _local_subscribe_user_to_room(self, user_id: str, room_id: str) -> None:
        """이 노드의 user_id 세션들을 `_room_subs[room_id]` 에 추가.

        unregister 진행 중인 dead WS 는 `_local_ws_by_session` 부재로 가드.
        """
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

        # 방의 마지막 구독자가 빠졌으면 빈 set 정리 (메모리 누수 방지)
        if room_set is not None and not room_set:
            del self._room_subs[room_id]


    async def _local_deliver_to_room(self, room_id: str, payload: dict) -> None:
        """`_room_subs[room_id]` 의 로컬 WS 전체에 push (발신 세션 skip)."""
        sender_sid = payload.get("sender_session_id")
        recipients = [
            ws for ws in self._room_subs.get(room_id, ())
            if ws.session_id != sender_sid
        ]
        await self._broadcast(recipients, payload)


    async def _local_deliver_to_user(self, user_id: str, payload: dict) -> None:
        """`_user_subs[user_id]` 의 로컬 WS 전체에 push."""
        recipients = list(self._user_subs.get(user_id, ()))
        await self._broadcast(recipients, payload)


    async def _local_deliver_to_session(self, session_id: str, payload: dict) -> None:
        """로컬 dict 에 해당 세션이 있으면 push, 없으면 silent drop."""
        ws = self._local_ws_by_session.get(session_id)
        if ws is None:
            return
        await self._broadcast([ws], payload)


    # ──────────────────── publish 헬퍼 (node_channel 모드) ────────────────────

    @staticmethod
    async def _publish_broadcast(envelope: dict) -> None:
        """활성 노드 전체의 `node:{node_id}` 채널에 publish (자기 자신 포함).

        자기 자신에게도 publish 하면 디스패처가 받아 `_local_*` 로 들어가는 통일 경로가
        유지된다. Redis publish 단일 round-trip (~1ms) 추가 latency.

        활성 노드 0 명이면 publish 자체를 skip — 단일 노드 운영 시작 직후 / shutdown
        직후의 race window 에서 의미 없는 PUBLISH 부담 회피.

        envelope 에 request_id / traceparent 를 박아 cross-node 추적을 보존한다 (Phase 5
        대비). dispatcher 가 contextvar 로 복원해 본 노드의 로그에서도 동일 ID 가 보인다.
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
        """특정 세션이 붙은 노드에만 publish.

        `ws_route:{sid}` 가 없으면 세션 만료/종료 — 직송 의미 없음. 조용히 drop
        (`in_process` 모드에서 `_local_ws_by_session` 부재 시와 동일 의미).
        """
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


    # ──────────────────── 내부 ────────────────────

    async def _broadcast(self, recipients: list[WebSocket], payload: dict) -> None:
        """여러 WS 에 동시 push — 한 WS 실패가 다른 WS 를 막지 않도록 `gather(return_exceptions=True)`.

        실패 처리 정책:
        - dead 세션 (RuntimeError / WebSocketDisconnect) 은 즉시 unregister.
          starlette 가 이미 닫힌 WS 에 대해 던지는 신호이므로 정리해도 안전하며,
          정리하지 않으면 매 fan-out 마다 좀비 세션에 반복 시도되어 워닝 폭발.
          (핸들러의 `finally` cleanup 이 race 로 누락된 경우의 안전망)
        - 그 외 예외는 일시적일 수 있으므로 정리하지 않고 로그만 남긴다.

        예외 클래스명만이 아니라 `repr(result)` 로 메시지까지 남겨 원인 파악이 가능하게.
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