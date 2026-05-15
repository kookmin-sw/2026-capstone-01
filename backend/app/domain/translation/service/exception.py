"""Translation 도메인 전용 커스텀 예외.

Router 가 HTTPException 으로 매핑 (§에러 처리 컨벤션):
    TranslationVendorError       → 502 (외부 번역 서비스 응답 실패: 4xx / 5xx)
    TranslationUnreachableError  → 504 (외부 번역 서비스에 도달 불가: 네트워크 / 타임아웃)

Service 가 vendor SDK (httpx 등) 의 예외를 위 도메인 예외로 변환해 던진다.
Router 는 도메인 예외만 알면 되므로 vendor 교체 시 router 변경 불필요.
"""


class TranslationError(Exception):
    """번역 도메인 공통 베이스."""


class TranslationVendorError(TranslationError):
    """외부 번역 서비스가 4xx / 5xx 응답 — Router 에서 502 로 매핑."""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"vendor responded {status_code}: {body}")


class TranslationUnreachableError(TranslationError):
    """외부 번역 서비스에 네트워크 도달 불가 / 타임아웃 — Router 에서 504 로 매핑."""
