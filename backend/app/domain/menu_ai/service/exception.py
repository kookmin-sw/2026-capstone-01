"""Menu OCR 도메인 전용 커스텀 예외.

Router 가 HTTPException 으로 매핑 (§에러 처리 컨벤션):
    MenuOcrCredentialExpiredError → 503 (Gemini API 키 만료 / 권한 거부 — 운영자 책임)
    MenuOcrQuotaExceededError     → 429 (Gemini 쿼터 소진 — RPM/TPM/일일 한도 — 클라이언트 백오프)
    MenuOcrVendorError            → 502 (Gemini 일시 장애 / 기타 5xx / 입력 거부)

Service 가 vendor SDK (langchain_google_genai → google.api_core) 의 예외를 위 도메인
예외로 변환해 던진다. Router 는 도메인 예외만 알면 되므로 vendor 교체 시 router 변경 불필요.
"""


class MenuOcrError(Exception):
    """메뉴 OCR 도메인 공통 베이스."""


class MenuOcrCredentialExpiredError(MenuOcrError):
    """Gemini 인증 만료 / 권한 거부 — Router 에서 503 으로 매핑.

    GOOGLE_GEMINI_API_KEY 가 만료되었거나 콘솔에서 회수된 경우. 외부 장애가 아니라
    운영자 책임이라 5xx 로 표면화해 알람을 트리거한다 (502 와 구분).
    """


class MenuOcrQuotaExceededError(MenuOcrError):
    """Gemini 쿼터 소진 — Router 에서 429 로 매핑.

    분당/일일 요청 수(RPM/RPD) 또는 토큰 수(TPM/TPD) 중 하나라도 한도에 도달하면 발생.
    langchain 측에서 6 번 재시도 후에도 회복되지 못한 경우 도달. 클라이언트는 백오프하면 됨.
    """


class MenuOcrVendorError(MenuOcrError):
    """Gemini 일시 장애 / 기타 GoogleAPICallError — Router 에서 502 으로 매핑."""
