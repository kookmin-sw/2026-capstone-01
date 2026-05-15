import uuid
from typing import Callable, Optional
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from fastapi import Request, Response

from app.core.logger import get_logger
from app.core.instrumentation import db_route_for_path
from app.core.context import db_route_var, request_id_var


class RequestIDMiddleware(BaseHTTPMiddleware):
    """요청 ID를 생성하고 추적하는 미들웨어"""
    
    def __init__(
        self,
        app: ASGIApp,
        header_name: str = "X-Request-ID",
        generator: Optional[Callable[[], str]] = None,
    ) -> None:
        super().__init__(app)
        self.header_name = header_name
        self.generator = generator or self._default_generator
        self.logger = get_logger("middleware.request_tracking")
    
    @staticmethod
    def _default_generator() -> str:
        """기본 요청 ID 생성기"""
        return str(uuid.uuid4())
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get(self.header_name) or self.generator()

        request.state.request_id = request_id

        # contextvar 에 set — FanoutService 등 깊은 호출 스택에서 envelope 에 박을 때 사용.
        rid_token = request_id_var.set(request_id)
        # DB query / transaction 메트릭의 route 라벨 — 도메인 단위 매핑.
        route_token = db_route_var.set(db_route_for_path(request.url.path))

        self.logger.bind(
            request_id=request_id,
            method=request.method,
            path=request.url.path
        ).debug("요청 ID 할당됨")

        try:
            response = await call_next(request)
        finally:
            db_route_var.reset(route_token)
            request_id_var.reset(rid_token)

        response.headers[self.header_name] = request_id

        return response


class ErrorTrackingMiddleware(BaseHTTPMiddleware):
    """에러 추적 및 모니터링 미들웨어."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.logger = get_logger("middleware.error_tracking")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        request_id = getattr(request.state, "request_id", "unknown")

        req_logger = self.logger.bind(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_host=request.client.host if request.client else None,
        )

        try:
            response = await call_next(request)

            process_time = time.perf_counter() - start_time
            response.headers["X-Process-Time"] = str(process_time)

            req_logger.bind(
                status_code=response.status_code,
                process_time=process_time,
            ).debug("요청 처리 완료")

            return response

        except Exception as e:
            process_time = time.perf_counter() - start_time
            req_logger.bind(
                error=str(e),
                error_type=type(e).__name__,
                process_time=process_time,
            ).error("요청 처리 중 에러 발생")
            raise


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """보안 헤더 추가 미들웨어"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        return response