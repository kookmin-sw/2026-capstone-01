"""채팅 도메인 전용 커스텀 예외.

Router 가 HTTPException 으로 매핑 (§에러 처리 컨벤션):
    ValueError             → 400
    PermissionError        → 403
    ChatRoomNotFoundError  → 404
    UpstreamError          → 500 (외부 저장소 지속 실패)
"""


class ChatRoomNotFoundError(ValueError):
    """요청된 chat_room 이 존재하지 않거나 이미 삭제됨 — Router 에서 404 로 매핑."""
    # WS op result 라벨용 self-classification — instrumentation._classify_ws_op_error 가 읽는다.
    # 클래스 rename 시에도 라벨 안정. ValueError subclass 라 isinstance 단독으론 'validation'
    # 으로 잘못 분류되니, instrumentation 은 error_kind 를 isinstance 보다 먼저 체크한다.
    error_kind = "not_found"


class UpstreamError(Exception):
    """외부 저장소 (MongoDB seq insert 등) 가 재시도 상한 내에 수렴하지 않음.

    Router 에서 500 으로 매핑한다. 정상 운영 중엔 이 예외가 발생하지 않아야 하며
    (`room:seq:*` 복구 이벤트 메트릭과 함께 추적), 발생 시 `dedupe:*` 키는 이미
    Service 가 삭제한 상태 → 클라가 동일 client_msg_id 로 재시도 가능.
    """
    # WS op result 라벨용 self-classification (위 ChatRoomNotFoundError 와 동일 패턴).
    error_kind = "upstream"
