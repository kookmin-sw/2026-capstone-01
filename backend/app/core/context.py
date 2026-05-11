"""contextvar 기반 트레이싱 컨텍스트.

요청 (HTTP / WebSocket) 단위로 request_id 와 traceparent 를 task-local 에 저장한다.
asyncio task 경계를 자동으로 따라가므로 깊은 호출 스택에서도 명시 인자 없이 회수 가능.

설정 위치:
  - HTTP: RequestIDMiddleware (request 처리 진입 시점)
  - WS: ws.py 의 op 수신 루프 (매 op 진입 시점)

사용 위치:
  - FanoutService 의 publish — envelope 에 박아 cross-node 추적 보존
  - 향후 OTel 도입 시 trace context 와 자연 연결

빈 문자열 default 로 두면 envelope serialize 시 KeyError 회피 + json 기본 직렬화 가능.
"""
from contextvars import ContextVar


request_id_var: ContextVar[str] = ContextVar("request_id", default="")
traceparent_var: ContextVar[str] = ContextVar("traceparent", default="")

# DB 메트릭의 route 라벨용 task-local 컨텍스트.
# HTTP 미들웨어 또는 워커 진입 시 set, SQLAlchemy 이벤트 리스너 / UoW __aexit__ 에서 read.
# 도메인 단위 enum 으로 통제 (instrumentation.py 의 db_route_for_path 참조).
db_route_var: ContextVar[str] = ContextVar("db_route", default="other")
