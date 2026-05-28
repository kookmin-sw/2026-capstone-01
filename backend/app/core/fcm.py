"""Firebase Cloud Messaging — Admin SDK 클라이언트 래퍼.

- FastAPI lifespan startup 에서 `init_fcm()` 1회 호출 → 디폴트 앱 등록.
- `firebase_admin` 자체가 디폴트 App 을 전역 보관하므로 별도 싱글톤 클래스를 두지
  않고 모듈 변수 한 개로 상태를 관리한다.
- `messaging.send()` 류 호출은 동기 SDK 이므로 호출자는 `asyncio.to_thread()` 로
  감싸 이벤트 루프를 막지 않도록 한다.
"""
from pathlib import Path
from firebase_admin import credentials
import firebase_admin

from app.core.logger import get_logger
from app.config.setting import settings


logger = get_logger("fcm")

_BACKEND_ROOT = Path(__file__).resolve().parents[2]   # app/core/fcm.py → backend/
_app: "firebase_admin.App | None" = None


def _resolve_cred_path() -> Path:
    """`settings.FCM_CREDENTIALS_PATH` 를 절대 경로로 해석.
    상대 경로면 backend/ 기준으로 해석해 CWD 의존성을 제거한다."""
    p = Path(settings.FCM_CREDENTIALS_PATH)
    return p if p.is_absolute() else _BACKEND_ROOT / p


def init_fcm() -> firebase_admin.App:
    """Firebase Admin SDK 초기화 — startup 에서 1회 호출.
    이미 초기화되어 있으면 기존 App 을 그대로 반환 (idempotent)."""
    global _app
    if _app is not None:
        return _app

    cred_path = _resolve_cred_path()
    if not cred_path.exists():
        raise RuntimeError(
            f"FCM 서비스 계정 키 파일을 찾을 수 없습니다: {cred_path}\n"
            "Firebase 콘솔 → 프로젝트 설정 → 서비스 계정 → 새 비공개 키 생성 후 위 경로에 저장하세요."
        )

    _app = firebase_admin.initialize_app(credentials.Certificate(str(cred_path)))
    logger.info("FCM 초기화 완료 (project_id={})", _app.project_id)
    return _app


def get_fcm_app() -> firebase_admin.App:
    """초기화된 Firebase Admin App 반환. `init_fcm()` 이후에만 호출 가능."""
    if _app is None:
        raise RuntimeError("FCM 이 초기화되지 않았습니다. init_fcm() 을 먼저 호출하세요.")
    return _app


def close_fcm() -> None:
    """Firebase Admin App 정리 — shutdown 에서 호출."""
    global _app
    if _app is not None:
        firebase_admin.delete_app(_app)
        _app = None
        logger.info("FCM 종료")
