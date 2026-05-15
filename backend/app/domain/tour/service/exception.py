"""Tour 도메인 전용 커스텀 예외.

Router 가 HTTPException 으로 매핑 (§에러 처리 컨벤션):
    ValueError                              → 400 (또는 endpoint 에 따라 404)
    PermissionError                         → 403
    TourPlanNotFoundError                   → 404 (plan_id 로 직접 조회한 plan 이 없음)
    TourPlanItemNotFoundError               → 404 (카드/플랜/URL 계층 불일치 모두 404 통일)
    TourRecommendCredentialExpiredError     → 503 (Gemini API 키 만료 / 권한 거부 — 운영자 책임)
    TourRecommendQuotaExceededError         → 429 (Gemini 쿼터 소진 — 클라이언트 백오프)
    TourRecommendVendorError                → 502 (Gemini 일시 장애 / 기타 GoogleAPICallError)
"""


class TourPlanNotFoundError(ValueError):
    """플랜을 찾을 수 없음 — Router 에서 404 로 매핑.

    plan_id 로 직접 조회했는데 row 가 없는 경우 (혹은 race 로 사라짐).
    plan-not-found 와 비즈니스 검증 (day_number 범위 등) 을 같은 endpoint 에서
    raise 하면 매핑이 갈리는데, 이 클래스로 분리하여 라우터가 404 / 400 분기 가능.
    """


class TourPlanItemNotFoundError(ValueError):
    """카드를 찾을 수 없음 — Router 에서 404 로 매핑.

    다음 세 케이스를 통합:
    - item_id 가 존재하지 않음
    - item 은 있는데 소속 plan 이 사라짐 (race)
    - URL 의 plan_id 와 item.plan_id 가 불일치 (URL 계층 위반)

    리소스 enumeration 방어를 위해 메시지는 모두 "존재하지 않는 카드입니다." 로 통일.
    """


# ──────────────────── 여행 추천 (Gemini LLM 기반) ────────────────────
#
# Service 가 vendor SDK (langchain_google_genai → google.api_core) 의 예외를 아래
# 도메인 예외로 변환해 던진다. Router 는 도메인 예외만 알면 되므로 vendor 교체 시
# router 변경 불필요. menu_ai 와 동일 컨벤션.


class TourRecommendError(Exception):
    """여행 추천 도메인 공통 베이스."""


class TourRecommendCredentialExpiredError(TourRecommendError):
    """Gemini 인증 만료 / 권한 거부 — Router 에서 503 으로 매핑.

    GOOGLE_GEMINI_API_KEY 가 만료되었거나 콘솔에서 회수된 경우. 외부 장애가 아니라
    운영자 책임이라 5xx 로 표면화해 알람을 트리거한다 (502 와 구분).
    """


class TourRecommendQuotaExceededError(TourRecommendError):
    """Gemini 쿼터 소진 — Router 에서 429 로 매핑.

    분당/일일 요청 수(RPM/RPD) 또는 토큰 수(TPM/TPD) 중 하나라도 한도에 도달하면 발생.
    langchain 측에서 6 번 재시도 후에도 회복되지 못한 경우 도달. 클라이언트는 백오프하면 됨.
    """


class TourRecommendVendorError(TourRecommendError):
    """Gemini 일시 장애 / 기타 GoogleAPICallError — Router 에서 502 으로 매핑."""
