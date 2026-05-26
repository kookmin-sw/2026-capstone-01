"""채팅 도메인 커스텀 예외 — Router 가 HTTP status 로 매핑."""


class ChatRoomNotFoundError(ValueError):
    """요청한 chat_room 이 존재하지 않거나 삭제됨 — 404 매핑."""
    # error_kind 는 WS op 라벨 분류용. instrumentation 이 isinstance 보다 먼저 읽는다.
    error_kind = "not_found"


class UpstreamError(Exception):
    """외부 저장소 (Mongo seq insert 등) 가 재시도 상한 내에 수렴 실패 — 500 매핑.

    이 예외가 나는 시점엔 dedupe 키가 이미 풀려 있어 같은 client_msg_id 로 재시도 가능.
    """
    error_kind = "upstream"
