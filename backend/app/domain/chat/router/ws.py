"""채팅 WebSocket 엔드포인트 — `/ws/chat`.

WS 업그레이드 핸드셰이크는 `BaseHTTPMiddleware` 를 거치지 않으므로 인증을
**이 모듈 내부에서 직접** 수행한다 (Origin 화이트리스트 + JWT + status 가드).

JWT 전송 채널
    - 웹: `utk` 쿠키 (httpOnly 자동 첨부)
    - 앱: Sec-WebSocket-Protocol 헤더 (브라우저 WebSocket API 가 임의 헤더를
      못 붙이는 제약 우회). 클라가 `['krip.chat.v1', 'auth.<jwt>']` 형태로 두 개의
      subprotocol 을 보내면 서버가 `auth.<jwt>` 에서 토큰 추출 + 검증 후
      `krip.chat.v1` 만 echo. `auth.<jwt>` 는 응답 헤더 노출 방지를 위해 echo 안 함.

연결 플로우
    1. Origin 헤더 화이트리스트 검증 → 실패 시 close(4403)
    2. JWT 검증 (쿠키 → subprotocol fallback) → 실패 시 close(4001)
    3. status 가드 (INACTIVE / 미가입 차단) → 실패 시 close(4019)
       `RegisterCheckMiddleware` 와 동일 검증을 `REGISTERED:{uid}` 캐시 공유로 수행.
    4. WS accept (subprotocol 인증 시 `krip.chat.v1` echo)
    5. SessionService.create_session — Redis 3키 + 세션 한도 체크
    6. WS 컨텍스트 심기 (session_id / user_id / subscribed_rooms)
    7. FanoutService.register_session + 방 목록 register_ws_to_room
    8. `connected` 이벤트 송신
    9. heartbeat 백그라운드 태스크 기동
    10. op 수신 루프 (매 op 진입 시 `session_exists` 체크 — revoke 감지)
    11. 종료 시: unregister_ws → Redis 정리 → WS close
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


# ──────────────────── 상수 ────────────────────

HEARTBEAT_INTERVAL = 30       # Redis TTL 연장 주기 (초)

# WS close codes
CLOSE_AUTH_EXPIRED = 4001
CLOSE_FORBIDDEN_ORIGIN = 4403
CLOSE_WITHDRAWAL_PENDING = 4019    # HTTP 419 (탈퇴 유예) 와 매칭
CLOSE_SERVICE_RESTART = 1012

# Sec-WebSocket-Protocol 서브프로토콜 — 앱 인증 채널
# 브라우저 WebSocket API 가 임의 헤더를 못 붙이는 제약을 우회.
SUBPROTOCOL_VERSION = "krip.chat.v1"
SUBPROTOCOL_AUTH_PREFIX = "auth."


# Pydantic discriminated union 어댑터는 모듈 레벨에서 1회만 생성
_ClientRequestAdapter = TypeAdapter(ClientRequest)


# ──────────────────── 메인 엔드포인트 ────────────────────

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
    # 1. Origin 검증
    origin = websocket.headers.get("origin")
    if not _is_allowed_origin(origin):
        logger.warning("WS 연결 거부 — 허용되지 않은 Origin: {}", origin)
        chat_ws_connect_result("origin_denied")
        await websocket.close(code=CLOSE_FORBIDDEN_ORIGIN)
        return

    # 2. JWT 검증 (쿠키 → subprotocol fallback)
    auth = _verify_jwt(websocket)
    if auth is None:
        chat_ws_connect_result("auth_expired")
        await websocket.close(code=CLOSE_AUTH_EXPIRED)
        return
    user_id, token_jti = auth

    # 3. status 가드 — `RegisterCheckMiddleware` 가 WS 우회되므로 동등한 INACTIVE /
    #    미가입 차단을 여기서 직접. REGISTERED 캐시 공유로 HTTP/WS 일관성 유지.
    if not await _check_user_active(websocket, user_id):
        logger.warning("WS 연결 거부 — INACTIVE / 미가입 유저: user_id={}", user_id)
        chat_ws_connect_result("auth_inactive")
        await websocket.close(code=CLOSE_WITHDRAWAL_PENDING)
        return

    # 4. 업그레이드 수락 — 앱이 subprotocol 인증을 사용했다면 krip.chat.v1 echo.
    #    웹(쿠키 플로우) 은 None → 응답에 Sec-WebSocket-Protocol 헤더 미포함.
    await websocket.accept(subprotocol=_select_accept_subprotocol(websocket))

    # 5. Redis 세션 등록 + 한도 체크
    try:
        session_id = await session_svc.create_session(user_id, token_jti)
    except Exception as e:
        logger.exception("세션 생성 실패: user_id={}, err={}", user_id, e)
        chat_ws_connect_result("session_failed")
        # 이 시점에 클라가 이미 끊겼다면 send/close 자체가 disconnect 예외를 던질 수 있음.
        # 아직 inc/register 전이라 cleanup 할 자원이 없으므로 조용히 흡수하고 반환.
        try:
            await websocket.send_json({"type": "server_error", "reason": "session_create_failed"})
        except Exception:
            pass
        try:
            await websocket.close(code=CLOSE_SERVICE_RESTART)
        except Exception:
            pass
        return

    # 정상 연결 — accept + session 모두 통과.
    chat_ws_connect_result("ok")
    chat_ws_connection_inc()

    # 6. WS 컨텍스트 심기 (FanoutService duck typing 전제)
    websocket.session_id = session_id  # type: ignore[attr-defined]
    websocket.user_id = user_id        # type: ignore[attr-defined]
    websocket.subscribed_rooms = set()  # type: ignore[attr-defined]

    # 7~10 단계는 모두 단일 try 안에서 수행 — init 단계 (connected 송신·unread 동기화·
    # heartbeat 생성) 중간에 클라가 끊겨도 finally cleanup 에 반드시 도달하도록 보장한다.
    # 한 짝이라도 누락되면 metric counter / fanout dict / Redis 세션 키가 누수.
    heartbeat_task: asyncio.Task | None = None
    try:
        # 7. 세션/방 등록
        fanout.register_session(websocket)
        try:
            room_ids = await room_svc.list_user_room_ids(user_id)
        except Exception as e:
            logger.exception("방 목록 로드 실패: user_id={}, err={}", user_id, e)
            room_ids = []
        for rid in room_ids:
            fanout.register_ws_to_room(websocket, rid)

        # 8. connected 이벤트 — 클라가 session_id 를 수신해 향후 비교/로깅에 사용.
        #    핸드셰이크 직후 즉시 close 하는 race 에서는 여기서 WebSocketDisconnect 가
        #    발생하지만, 외곽 except 가 정상 종료로 흡수 + finally 가 cleanup 한다.
        await websocket.send_json({"type": "connected", "session_id": session_id})

        # 8-a. unread 초기 동기화 — Redis 에 값이 있으면 즉시 push, 없으면 백그라운드 복구.
        #   복구 완료 시 `unread_synced` 를 뒤늦게라도 push 해 클라 UI 가 싱크되도록 한다.
        #   recover 자체는 RDB + Mongo count 조합이라 느릴 수 있으므로 fire-and-forget.
        try:
            counts = await history_svc.get_unread_counts(user_id)
            if counts:
                await websocket.send_json({"type": "unread_synced", "counts": counts})
            else:
                # Redis 비어있음 → Phase 3 복구 경로. 태스크 참조는 _spawn_* 가 내부 set 에 보관.
                _spawn_recover_unread(websocket, user_id)
        except WebSocketDisconnect:
            # 외곽 except 에서 정상 종료 + finally cleanup 으로 위임.
            raise
        except Exception as e:
            logger.warning("unread 동기화 실패 (무시하고 진행): user_id={}, err={!r}", user_id, e)

        # 9. heartbeat 백그라운드 태스크
        heartbeat_task = asyncio.create_task(
            _heartbeat_loop(session_svc, session_id, user_id),
            name=f"chat-hb-{session_id}",
        )

        # 10. op 수신 루프
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
        # 11. 종료 순서: ① metric → ② 로컬 dict → ③ heartbeat 정리 대기 → ④ Redis 정리.
        # 각 단계는 서로 독립이므로 한 쪽 실패가 다음 단계를 막지 않도록 개별 try 로 격리한다.
        # cleanup path 는 본 요청 처리가 끝난 뒤이므로 warning 으로만 남기고 진행한다.
        # (CancelledError 는 BaseException 이라 `except Exception` 에 잡히지 않아 정상 전파됨)
        chat_ws_connection_dec()

        try:
            fanout.unregister_ws(websocket)
        except Exception as e:
            logger.warning(
                "fanout unregister 실패 (무시): session_id={}, err={}", session_id, e,
            )

        # heartbeat_task 가 None 이면 init 단계 disconnect 로 생성 전 — cancel 스킵.
        # cancel 만 하고 반환하면 pending 상태로 GC 되어 "Task was destroyed but it is
        # pending!" 경고 노이즈 + 리소스 누수 위험. gather(return_exceptions=True) 로
        # CancelledError 소화까지 기다림 (bounded).
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


# ──────────────────── unread 백그라운드 복구 ────────────────────

# 활성 복구 태스크 강한 참조 — Python asyncio 가 `create_task` 반환값을 버리면
# GC 가 태스크를 중간에 수거할 수 있다는 공식 경고에 대응. 완료 시 self-remove.
_ACTIVE_RECOVER_TASKS: set[asyncio.Task] = set()


def _spawn_recover_unread(websocket: WebSocket, user_id: str) -> None:
    """`_recover_unread_and_notify` 를 백그라운드 태스크로 spawn 하고 참조를 보관.

    모듈 상수 `_ACTIVE_RECOVER_TASKS` 에 강한 참조를 유지해 중간 GC 방지. `add_done_callback`
    으로 완료 시 self-remove — 장시간 켜진 서버에서 집합이 누적되지 않도록.
    """
    task = asyncio.create_task(
        _recover_unread_and_notify(websocket, user_id),
        name=f"chat-unread-recover-{user_id}",
    )
    _ACTIVE_RECOVER_TASKS.add(task)
    task.add_done_callback(_ACTIVE_RECOVER_TASKS.discard)


async def _recover_unread_and_notify(websocket: WebSocket, user_id: str) -> None:
    """recover_unread_for_user 실행 후 WS 가 여전히 살아있으면 결과를 push.

    복구는 RDB + Mongo count 조합이라 수 초 걸릴 수 있으므로 WS 핸들러를 블로킹하지 않기
    위해 fire-and-forget 태스크로 호출된다. 태스크가 끝나기 전에 WS 가 끊길 수 있으므로
    connection state 를 확인한 뒤 전송. 실패는 warning 로그만.
    """
    try:
        counts = await recover_unread_for_user(user_id)
    except Exception as e:
        logger.warning("unread 백그라운드 복구 실패: user_id={}, err={}", user_id, e)
        return

    if not counts:
        # Redis 반영 실패로 recover 가 빈 dict 을 돌려줬을 수 있음 — WS push 생략.
        # 다음 재연결에서 다시 시도됨 (Redis 여전히 비어있기 때문).
        return

    # WS 가 이미 닫혔으면 send_json 이 예외를 던짐 — 조용히 먹음
    try:
        await websocket.send_json({"type": "unread_synced", "counts": counts})
    except Exception as e:
        logger.debug(
            "unread 복구 결과 push 실패 (WS 이미 종료 가능): user_id={}, err={}",
            user_id, type(e).__name__,
        )


# ──────────────────── 인증 ────────────────────

def _is_allowed_origin(origin: str | None) -> bool:
    """Origin 화이트리스트 검증.

    웹 프론트 origin (CORS allow_origins 과 동일) + 앱 (Capacitor 등) origin 합집합.
    앱 origin 은 `settings.APP_ALLOWED_ORIGINS` 에서 환경별로 관리한다.
    """
    if origin is None:
        return False
    allowed = {settings.FRONTEND_URL, settings.LOCAL_FRONTEND_URL} | settings.app_allowed_origins
    return origin in allowed


def _ws_subprotocols(websocket: WebSocket) -> list[str]:
    """클라가 핸드셰이크로 요청한 Sec-WebSocket-Protocol 목록을 파싱."""
    header = websocket.headers.get("sec-websocket-protocol", "")
    return [p.strip() for p in header.split(",") if p.strip()]


def _extract_jwt(websocket: WebSocket) -> str | None:
    """JWT 추출. 쿠키(웹) → Sec-WebSocket-Protocol(앱) 순.

    웹은 자동 첨부된 쿠키로 통과되고, 앱은 `auth.<jwt>` subprotocol 로 통과된다.
    동시 전송 시나리오는 실무상 없지만 (각 클라이언트가 자기 채널만 사용), 우선순위는
    쿠키 → subprotocol 로 두어 기존 웹 동작을 그대로 보존한다.
    """
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
    """핸드셰이크 accept 시 응답할 subprotocol 선택.

    클라가 `krip.chat.v1` 도 함께 요청했을 때만 그것을 echo. `auth.<jwt>` 는 토큰이라
    절대 echo 하지 않는다 (응답 헤더 노출 방지).

    클라가 어떤 subprotocol 도 안 보냈으면 (= 웹 쿠키 플로우) None 반환 → 응답 헤더 미포함.
    """
    if SUBPROTOCOL_VERSION in _ws_subprotocols(websocket):
        return SUBPROTOCOL_VERSION
    return None


def _verify_jwt(websocket: WebSocket) -> tuple[str, str] | None:
    """JWT 를 검증해 (user_id, token_jti) 반환. 실패 시 None.

    token_jti 는 JWT `jti` claim 이 없으면 token 앞 32자를 fallback 으로 사용 —
    이는 SessionService 가 `sess:{sid}.token_jti` 에 기록만 하고 현재는 비교하지 않기
    때문. refresh 시점에 같은 로직으로 비교하면 일관성 유지.
    """
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
    token_jti = payload.get("jti") or token[:32]
    return str(user_id), str(token_jti)


async def _check_user_active(websocket: WebSocket, user_id: str) -> bool:
    """INACTIVE / 미가입 차단 — `RegisterCheckMiddleware` 와 동등한 가드.

    WS 는 `BaseHTTPMiddleware` 를 거치지 않아 미들웨어의 status 검증이 우회된다. 같은
    로직을 핸드셰이크에서 직접 수행하되, `REGISTERED:{uid}` 캐시 키를 **공유** 해
    HTTP/WS 간 중복 DB 조회 방지 + 일관성 유지.

    검증 항목 (미들웨어 line 280~308 과 동일):
        - 유저 미존재 → 차단
        - status == INACTIVE (탈퇴 유예) → 차단
        - user.detail 없음 (2차 가입 미완료) → 차단
        - 그 외 → 캐시 set 후 통과

    Fail policy:
        DB 장애 시 fail-closed (False 반환) — 의심스러우면 차단. 클라가 재시도하면 캐시
        hit 으로 통과 가능하고 (양성 결과 캐싱), 영구 장애가 아니라면 자연 복구된다.

    Returns:
        True  — ACTIVE & 2차 가입 완료 (캐시 hit 또는 DB 양성)
        False — INACTIVE / 미가입 / 미존재 / DB 장애
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


# ──────────────────── op 수신 루프 ────────────────────

async def _receive_loop(
    *,
    websocket: WebSocket,
    session_id: str,
    user_id: str,
    session_svc: SessionService,
    chat_svc: MessageService,
    room_svc: RoomService,
) -> None:
    """op 디스패처. 매 op 진입 시 Redis 에서 세션 유효성 확인."""
    while True:
        raw = await websocket.receive_json()

        # 매 op 진입 시 revoke 감지 (§3.4)
        if not await session_svc.session_exists(session_id):
            await websocket.send_json({"type": "auth_expired"})
            await websocket.close(code=CLOSE_AUTH_EXPIRED)
            return

        # op 단위 request_id contextvar 셋팅 — fanout publish 시 envelope 에 박힌다.
        op_request_id = str(uuid.uuid4())
        rid_token = request_id_var.set(op_request_id)

        # op 파싱 — 실패 시 op 라벨이 unknown 으로 잡혀도 의미 살아있다.
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

        # 분기 처리 — chat_ws_op 가 result 카운트를 자동 처리한다.
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
            # read op 는 `read_failed` 이벤트로 실패 사유를 전달 — 다른 op 는
            # `server_error` 규약 유지.
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
            # 외부 저장소 지속 실패 — 연결은 유지, 클라가 재시도 가능
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
    """`op=send` — MessageService.send_message 실행 후 ACK 직송."""
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
    """`op=refresh` — JWT 재검증 후 `sess:{sid}.token_jti` 갱신. session_id 는 유지."""
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
    """`op=read` — RoomService.mark_read 로 포인터 갱신 + ack/fan-out.

    `mark_read` 내부에서 `read_ack` 발신 세션 직송 + `read` 이벤트 방 브로드캐스트까지
    수행하므로 여기서는 별도 추가 전송이 없다. 실패 시 예외는 `_receive_loop` 의
    분기에서 `read_failed` 로 변환된다.
    """
    await room_svc.mark_read(
        me_id=user_id,
        me_session_id=session_id,
        room_id=req.room_id,
        up_to_server_seq=req.up_to_server_seq,
    )


# ──────────────────── heartbeat ────────────────────

async def _heartbeat_loop(
    session_svc: SessionService,
    session_id: str,
    user_id: str,
) -> None:
    """`HEARTBEAT_INTERVAL` 초마다 Redis TTL 연장. 메인 루프 종료 시 cancel 됨."""
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
