"""채팅 WebSocket 엔드포인트 — `/ws/chat`.

WS 업그레이드는 `BaseHTTPMiddleware` 를 거치지 않아 인증을 이 모듈에서 직접 수행.

JWT 전송 채널:
- 웹: `utk` 쿠키 (httpOnly 자동 첨부)
- 앱: `Sec-WebSocket-Protocol` 헤더 — 브라우저 WebSocket API 가 임의 헤더를 못 붙이는 제약 우회.
       클라가 `['krip.chat.v1', 'auth.<jwt>']` 형태로 보내면 서버가 `krip.chat.v1` 만 echo
       (`auth.<jwt>` 는 응답 헤더 노출 방지).
"""
import uuid
from pydantic import TypeAdapter, ValidationError
import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from dependency_injector.wiring import Provide, inject
import asyncio

from app.domain.chat.worker.reconcile import recover_unread_for_user
from app.domain.chat.service.session import SessionService
from app.domain.chat.service.room import RoomService
from app.domain.chat.service.message_history import MessageHistoryService
from app.domain.chat.service.message import MessageService
from app.domain.chat.service.fanout import FanoutService
from app.domain.chat.service.exception import ChatRoomNotFoundError, UpstreamError
from app.domain.chat.schema.ws_event import ClientRequest, ReadOp, RefreshOp, SendOp
from app.domain.auth.repository.user import UserRepository
from app.domain.auth.model.user import UserStatus
from app.core.redis import RedisClient
from app.core.logger import get_logger
from app.core.instrumentation import (
    chat_message_send_timer,
    chat_ws_connect_result,
    chat_ws_connection_dec,
    chat_ws_connection_inc,
    chat_ws_op,
    chat_ws_op_validation_failure,
)
from app.core.context import request_id_var
from app.core.cache.redis_cache import get_redis_cache_manager
from app.core.cache.key_category import KeyCategory
from app.container import Container
from app.config.setting import settings


router = APIRouter()
logger = get_logger("chat.ws")


HEARTBEAT_INTERVAL = 30

# WS close codes
CLOSE_AUTH_EXPIRED = 4001
CLOSE_FORBIDDEN_ORIGIN = 4403
CLOSE_WITHDRAWAL_PENDING = 4019    # HTTP 419 (탈퇴 유예) 와 매칭
CLOSE_SERVICE_RESTART = 1012

SUBPROTOCOL_VERSION = "krip.chat.v1"
SUBPROTOCOL_AUTH_PREFIX = "auth."


# 모듈 레벨에서 1회 생성.
_ClientRequestAdapter = TypeAdapter(ClientRequest)


@router.websocket("/chat")
@inject
async def ws_chat(
    websocket: WebSocket,
    fanout: FanoutService = Depends(Provide[Container.fanout_service]),
    session_svc: SessionService = Depends(Provide[Container.session_service]),
    room_svc: RoomService = Depends(Provide[Container.room_service]),
    chat_svc: MessageService = Depends(Provide[Container.message_service]),
    history_svc: MessageHistoryService = Depends(Provide[Container.message_history_service]),
) -> None:
    origin = websocket.headers.get("origin")
    if not _is_allowed_origin(origin):
        logger.warning("WS 연결 거부 — 허용되지 않은 Origin: {}", origin)
        chat_ws_connect_result("origin_denied")
        await websocket.close(code=CLOSE_FORBIDDEN_ORIGIN)
        return

    auth = _verify_jwt(websocket)
    if auth is None:
        chat_ws_connect_result("auth_expired")
        await websocket.close(code=CLOSE_AUTH_EXPIRED)
        return
    user_id, token_jti = auth

    # status 가드 — RegisterCheckMiddleware 가 WS 우회되므로 동등 검증을 직접 수행.
    if not await _check_user_active(websocket, user_id):
        logger.warning("WS 연결 거부 — INACTIVE / 미가입 유저: user_id={}", user_id)
        chat_ws_connect_result("auth_inactive")
        await websocket.close(code=CLOSE_WITHDRAWAL_PENDING)
        return

    # 앱이 subprotocol 인증을 사용했으면 krip.chat.v1 만 echo.
    await websocket.accept(subprotocol=_select_accept_subprotocol(websocket))

    try:
        session_id = await session_svc.create_session(user_id, token_jti)
    except Exception as e:
        logger.exception("세션 생성 실패: user_id={}, err={}", user_id, e)
        chat_ws_connect_result("session_failed")
        # 클라가 이미 끊겼다면 send/close 자체가 disconnect 예외를 던질 수 있음 — 조용히 흡수.
        try:
            await websocket.send_json({"type": "server_error", "reason": "session_create_failed"})
        except Exception:
            pass
        try:
            await websocket.close(code=CLOSE_SERVICE_RESTART)
        except Exception:
            pass
        return

    chat_ws_connect_result("ok")
    chat_ws_connection_inc()

    # FanoutService duck typing 전제.
    websocket.session_id = session_id  # type: ignore[attr-defined]
    websocket.user_id = user_id        # type: ignore[attr-defined]
    websocket.subscribed_rooms = set()  # type: ignore[attr-defined]

    # init 중 클라가 끊겨도 finally cleanup 에 도달하도록 단일 try 안에서 진행.
    heartbeat_task: asyncio.Task | None = None
    try:
        fanout.register_session(websocket)
        try:
            room_ids = await room_svc.list_user_room_ids(user_id)
        except Exception as e:
            logger.exception("방 목록 로드 실패: user_id={}, err={}", user_id, e)
            room_ids = []
        for rid in room_ids:
            fanout.register_ws_to_room(websocket, rid)

        await websocket.send_json({"type": "connected", "session_id": session_id})

        # unread 초기 동기화 — Redis 가 비면 백그라운드 복구 (RDB+Mongo 기반이라 느릴 수 있음).
        try:
            counts = await history_svc.get_unread_counts(user_id)
            if counts:
                await websocket.send_json({"type": "unread_synced", "counts": counts})
            else:
                _spawn_recover_unread(websocket, user_id)
        except WebSocketDisconnect:
            raise
        except Exception as e:
            logger.warning("unread 동기화 실패 (무시하고 진행): user_id={}, err={!r}", user_id, e)

        heartbeat_task = asyncio.create_task(
            _heartbeat_loop(session_svc, session_id, user_id),
            name=f"chat-hb-{session_id}",
        )

        await _receive_loop(
            websocket=websocket,
            session_id=session_id,
            user_id=user_id,
            session_svc=session_svc,
            chat_svc=chat_svc,
            room_svc=room_svc,
        )
    except WebSocketDisconnect:
        logger.debug("WS 정상 종료: session_id={}", session_id)
    except Exception as e:
        logger.exception("WS 핸들러 예외: session_id={}, err={}", session_id, e)
    finally:
        # 종료 순서: metric → 로컬 dict → heartbeat → Redis. 각 단계 독립 try 로 격리.
        chat_ws_connection_dec()

        try:
            fanout.unregister_ws(websocket)
        except Exception as e:
            logger.warning(
                "fanout unregister 실패 (무시): session_id={}, err={}", session_id, e,
            )

        # heartbeat_task None 이면 init 단계 disconnect 로 생성 전. cancel 만 하고 반환하면
        # pending 상태로 GC 되어 경고 + 누수 위험 — gather 로 CancelledError 소화까지 대기.
        if heartbeat_task is not None:
            try:
                heartbeat_task.cancel()
                await asyncio.gather(heartbeat_task, return_exceptions=True)
            except Exception as e:
                logger.warning(
                    "heartbeat 정리 실패 (무시): session_id={}, err={}", session_id, e,
                )

        try:
            await session_svc.terminate_session(session_id, user_id)
        except Exception as e:
            logger.warning("세션 종료 실패 (무시): session_id={}, err={}", session_id, e)


# 활성 복구 task 강한 참조 — `create_task` 반환값을 버리면 GC 가 수거 가능. 완료 시 self-remove.
_ACTIVE_RECOVER_TASKS: set[asyncio.Task] = set()


def _spawn_recover_unread(websocket: WebSocket, user_id: str) -> None:
    """`_recover_unread_and_notify` 를 백그라운드로 spawn 하고 참조 보관."""
    task = asyncio.create_task(
        _recover_unread_and_notify(websocket, user_id),
        name=f"chat-unread-recover-{user_id}",
    )
    _ACTIVE_RECOVER_TASKS.add(task)
    task.add_done_callback(_ACTIVE_RECOVER_TASKS.discard)


async def _recover_unread_and_notify(websocket: WebSocket, user_id: str) -> None:
    """recover 후 WS 가 살아있으면 결과 push. 끊겼으면 조용히 drop."""
    try:
        counts = await recover_unread_for_user(user_id)
    except Exception as e:
        logger.warning("unread 백그라운드 복구 실패: user_id={}, err={}", user_id, e)
        return

    if not counts:
        # Redis 반영 실패로 빈 dict 가 올 수 있음 — 다음 재연결에서 재시도됨.
        return

    try:
        await websocket.send_json({"type": "unread_synced", "counts": counts})
    except Exception as e:
        logger.debug(
            "unread 복구 결과 push 실패 (WS 이미 종료 가능): user_id={}, err={}",
            user_id, type(e).__name__,
        )


def _is_allowed_origin(origin: str | None) -> bool:
    """웹 + 앱 origin 화이트리스트 검증."""
    if origin is None:
        return False
    allowed = {settings.FRONTEND_URL, settings.LOCAL_FRONTEND_URL} | settings.app_allowed_origins
    return origin in allowed


def _ws_subprotocols(websocket: WebSocket) -> list[str]:
    header = websocket.headers.get("sec-websocket-protocol", "")
    return [p.strip() for p in header.split(",") if p.strip()]


def _extract_jwt(websocket: WebSocket) -> str | None:
    """JWT 추출 — 쿠키(웹) 우선, 그 다음 `auth.<jwt>` subprotocol(앱)."""
    cookie_token = websocket.cookies.get(settings.USER_LOGIN_COOKIE_NAME)
    if cookie_token:
        return cookie_token

    for proto in _ws_subprotocols(websocket):
        if proto.startswith(SUBPROTOCOL_AUTH_PREFIX):
            token = proto[len(SUBPROTOCOL_AUTH_PREFIX):]
            if token:
                return token

    return None


def _select_accept_subprotocol(websocket: WebSocket) -> str | None:
    """클라가 `krip.chat.v1` 도 요청했을 때만 echo. `auth.<jwt>` 는 절대 echo 하지 않음."""
    if SUBPROTOCOL_VERSION in _ws_subprotocols(websocket):
        return SUBPROTOCOL_VERSION
    return None


def _verify_jwt(websocket: WebSocket) -> tuple[str, str] | None:
    """JWT 검증 후 `(user_id, token_jti)` 반환. 실패는 None."""
    token = _extract_jwt(websocket)
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.USER_LOGIN_JWT_SECRET_KEY,
            algorithms=[settings.USER_LOGIN_JWT_ALGORITHM],
        )
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

    user_id = payload.get("user_id")
    if not user_id:
        return None
    # jti claim 없으면 token 앞 32자 fallback — refresh 시 같은 로직 적용해야 일관.
    token_jti = payload.get("jti") or token[:32]
    return str(user_id), str(token_jti)


async def _check_user_active(websocket: WebSocket, user_id: str) -> bool:
    """INACTIVE / 미가입 차단. `REGISTERED:{uid}` 캐시를 HTTP 와 공유해 중복 DB 조회 회피.

    검증: 유저 존재 / status=ACTIVE / detail 존재 (2차 가입 완료).
    DB 장애 시 fail-closed — 의심스러우면 차단.
    """
    cache = get_redis_cache_manager()
    cache_key = f"{KeyCategory.REGISTERED}:{user_id}"

    if await cache.exists(cache_key):
        return True

    try:
        container = websocket.app.container
        async with container.uow() as session:
            user_repo = UserRepository(session)
            user = await user_repo.find_by_id_with_profile(user_id)
    except Exception as e:
        logger.warning(
            "WS status 가드 — DB 조회 실패 (fail-closed): user_id={}, err={}",
            user_id, type(e).__name__,
        )
        return False

    if user is None:
        return False
    if user.status != UserStatus.ACTIVE:
        return False
    if user.detail is None:
        return False

    await cache.set_flag(cache_key, RedisClient.DEFAULT_CACHE_TTL)
    return True


async def _receive_loop(
    *,
    websocket: WebSocket,
    session_id: str,
    user_id: str,
    session_svc: SessionService,
    chat_svc: MessageService,
    room_svc: RoomService,
) -> None:
    """op 디스패처. 매 op 진입 시 Redis 로 세션 유효성 확인."""
    while True:
        raw = await websocket.receive_json()

        if not await session_svc.session_exists(session_id):
            await websocket.send_json({"type": "auth_expired"})
            await websocket.close(code=CLOSE_AUTH_EXPIRED)
            return

        # op 단위 request_id — fanout publish 시 envelope 에 박힘.
        op_request_id = str(uuid.uuid4())
        rid_token = request_id_var.set(op_request_id)

        op_label = raw.get("op", "unknown") if isinstance(raw, dict) else "unknown"
        try:
            req = _ClientRequestAdapter.validate_python(raw)
        except ValidationError as e:
            first_err = e.errors()[0] if e.errors() else {}
            chat_ws_op_validation_failure(op_label)
            await websocket.send_json({
                "type": "server_error",
                "reason": f"invalid op: {first_err.get('msg', 'validation failed')}",
            })
            request_id_var.reset(rid_token)
            continue

        try:
            async with chat_ws_op(op_label):
                if isinstance(req, SendOp):
                    await _handle_send(
                        websocket=websocket,
                        session_id=session_id,
                        user_id=user_id,
                        chat_svc=chat_svc,
                        req=req,
                    )
                elif isinstance(req, RefreshOp):
                    await _handle_refresh(
                        websocket=websocket,
                        session_id=session_id,
                        user_id=user_id,
                        session_svc=session_svc,
                        req=req,
                    )
                elif isinstance(req, ReadOp):
                    await _handle_read(
                        websocket=websocket,
                        session_id=session_id,
                        user_id=user_id,
                        room_svc=room_svc,
                        req=req,
                    )
        except PermissionError as e:
            # read op 는 `read_failed` 이벤트로, 다른 op 는 `server_error` 규약.
            if isinstance(req, ReadOp):
                await websocket.send_json({
                    "type": "read_failed", "room_id": req.room_id, "reason": str(e),
                })
            else:
                await websocket.send_json({"type": "server_error", "reason": str(e)})
        except ValueError as e:
            if isinstance(req, ReadOp):
                await websocket.send_json({
                    "type": "read_failed", "room_id": req.room_id, "reason": str(e),
                })
            else:
                await websocket.send_json({"type": "server_error", "reason": str(e)})
        except ChatRoomNotFoundError as e:
            if isinstance(req, ReadOp):
                await websocket.send_json({
                    "type": "read_failed", "room_id": req.room_id, "reason": str(e),
                })
            else:
                await websocket.send_json({"type": "server_error", "reason": str(e)})
        except UpstreamError as e:
            await websocket.send_json({"type": "server_error", "reason": str(e)})
        finally:
            request_id_var.reset(rid_token)


async def _handle_send(
    *,
    websocket: WebSocket,
    session_id: str,
    user_id: str,
    chat_svc: MessageService,
    req: SendOp,
) -> None:
    """`op=send` — send_message 실행 후 ACK 직송."""
    fanout_path = (
        "cross_node" if settings.FANOUT_MODE == "node_channel" else "local"
    )
    async with chat_message_send_timer(fanout_path):
        ack = await chat_svc.send_message(
            sender_user_id=user_id,
            sender_session_id=session_id,
            room_id=req.room_id,
            client_msg_id=req.client_msg_id,
            msg_type=req.type,
            content=req.content,
        )
    await websocket.send_json({
        "type": "message.sent",
        "client_msg_id": ack.client_msg_id,
        "message_id": ack.message_id,
        "server_seq": ack.server_seq,
        "created_at": ack.created_at.isoformat(),
    })


async def _handle_refresh(
    *,
    websocket: WebSocket,
    session_id: str,
    user_id: str,
    session_svc: SessionService,
    req: RefreshOp,
) -> None:
    """`op=refresh` — JWT 재검증 후 token_jti 만 갱신. session_id 는 유지."""
    try:
        payload = jwt.decode(
            req.token,
            settings.USER_LOGIN_JWT_SECRET_KEY,
            algorithms=[settings.USER_LOGIN_JWT_ALGORITHM],
        )
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        await websocket.send_json({"type": "auth_expired"})
        await websocket.close(code=CLOSE_AUTH_EXPIRED)
        return

    if payload.get("user_id") != user_id:
        await websocket.send_json({"type": "auth_expired"})
        await websocket.close(code=CLOSE_AUTH_EXPIRED)
        return

    new_jti = payload.get("jti") or req.token[:32]
    await session_svc.update_token_jti(session_id, new_jti)


async def _handle_read(
    *,
    websocket: WebSocket,
    session_id: str,
    user_id: str,
    room_svc: RoomService,
    req: ReadOp,
) -> None:
    """`op=read` — mark_read 내부에서 `read_ack` 직송 + `read` 브로드캐스트까지 처리."""
    await room_svc.mark_read(
        me_id=user_id,
        me_session_id=session_id,
        room_id=req.room_id,
        up_to_server_seq=req.up_to_server_seq,
    )


async def _heartbeat_loop(
    session_svc: SessionService,
    session_id: str,
    user_id: str,
) -> None:
    """`HEARTBEAT_INTERVAL` 초마다 Redis TTL 연장. 메인 루프 종료 시 cancel."""
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await session_svc.heartbeat(session_id, user_id)
            except Exception as e:
                logger.warning(
                    "heartbeat 실패 (계속 진행): session_id={}, err={}", session_id, e,
                )
    except asyncio.CancelledError:
        raise
