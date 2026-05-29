""" 
로깅 설정

- 예시:
  LOG_LEVEL=DEBUG
  LOG_FORMAT=console
  LOG_FILE_PATH=/backend/logs/app.log

필드 설명:
  LOG_LEVEL:
    - 최소 출력 로그 레벨
    - TRACE < DEBUG < INFO < SUCCESS < WARNING < ERROR < CRITICAL
    - 여기서 설정한 레벨 "이상" 만 출력됨

  LOG_FORMAT:
    - "json"   : serialize=True 로 JSON 구조화 로그 출력 (로그 수집/분석용)
    - "console": 사람이 읽기 좋은 컬러 콘솔 로그 출력 (로컬 디버깅용)

  LOG_FILE_PATH:
    - None 이면 콘솔에만 출력
    - 경로를 지정하면 해당 파일로도 로그를 남김

  LOG_ROTATION:
    - "100 MB" → 로그 파일이 100MB를 넘으면 새 파일로 롤테이션
    - 용량/시간 기준 문자열 모두 사용 가능 (Loguru 규칙 따름)

  LOG_RETENTION:
    - "30 days" → 생성된 지 30일이 지난 롤테이션된 로그 파일은 자동 삭제

  LOG_COMPRESSION:
    - "gz" → 롤테이션된 로그 파일을 gzip(.gz)으로 압축


로깅 시스템

from core.exception.logger import get_logger

logger = get_logger("service_name")

logger.bind(user_id=123).bind(user_type="he").info("서비스 완료")
logger.bind(user_id=123, user_type="he").info("서비스 완료")


포맷팅 컨벤션:
  - f-string 대신 loguru의 {} 포맷 사용
  - 로그 레벨이 비활성화된 경우 문자열 조합을 건너뛰어 불필요한 연산 방지

  사용법:
    logger.info("유저: {}", user_id)               # {} : 범용 (str() 호출)
    logger.info("처리 시간: {:.2f}초", elapsed)     # {:.2f} : 소수점 2자리 실수
    logger.debug("입력값: {!r}", some_input)        # {!r} : repr() 출력 (타입 확인용)
    logger.info("개수: {:d}개", count)              # {:d} : 정수

  주의:
    logger.info(f"유저: {user_id}")                # (X) 레벨 비활성이어도 f-string 항상 평가됨
    logger.info("유저: {}", user_id)               # (O) 레벨 비활성이면 포맷팅 생략
"""
import sys
from pathlib import Path
from loguru._logger import Logger
from loguru import logger  
import logging

from app.config.setting import settings


def setup_logging() -> None:
    """로깅 시스템 설정"""

    # PROD 환경에서 console 포맷이면 Promtail 의 JSON parser 가 깨져 라벨이
    # 모두 unknown 으로 들어가고 14일치 로그 검색 불가가 된다. 운영자가 .env 에서
    # LOG_FORMAT 을 잊거나 잘못 설정해도 안전하도록 fail-safe 로 json 강제.
    #
    # 결정과 적용을 분리하는 이유:
    #   logger.remove() 와 logger.add() 사이에서 logger.warning() 을 호출하면 sink
    #   부재 구간이라 메시지가 어디에도 남지 않아 fail-safe 발화 자체가 silent 가
    #   된다 — 본 보호 로직의 의도(운영자 알림)가 깨지는 결함. 결정만 먼저 하고
    #   sink 가 모두 ready 된 뒤 함수 끝에서 emit.
    requested_format = settings.LOG_FORMAT
    forced_json = settings.is_production and requested_format != "json"
    log_format = "json" if forced_json else requested_format

    logger.remove()

    # 콘솔 출력 설정
    if log_format == "json":
        # JSON 포맷
        logger.add(
            sys.stdout,
            format="{message}",
            serialize=True,
            level=settings.LOG_LEVEL,
            enqueue=True
        )
    else:
        # 읽기 쉬운 콘솔 포맷
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level> | {extra}",
            level=settings.LOG_LEVEL,
            colorize=True,
            enqueue=True
        )
    
    # 파일 출력 설정
    if settings.LOG_FILE_PATH:
        log_path = Path(settings.LOG_FILE_PATH)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.add(
            settings.LOG_FILE_PATH,
            rotation=settings.LOG_ROTATION,
            retention=settings.LOG_RETENTION,
            compression=settings.LOG_COMPRESSION,
            format="{message}",
            serialize=True,
            level="INFO",
            encoding="utf-8",
            enqueue=True
        )
    
    # 표준 logging 라이브러리와 통합
    class InterceptHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            # loguru 레벨로 변환
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno
            
            # 해당 로거에서 발생한 로그 찾기
            frame, depth = logging.currentframe(), 2
            while frame and frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1
            
            logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())
    
    # 표준 로거 설정
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    
    # 주요 라이브러리 로거 레벨 설정.
    # uvicorn.access 는 DEBUG — RED 메트릭이 path/method/status/duration 제공하므로
    # 매 요청 INFO 출력은 중복 + PROD 로그 비용.
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.DEBUG)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # fail-safe 발화 알림 — sink 가 모두 ready 된 시점이라 stdout/JSON sink 와
    # LOG_FILE_PATH 양쪽에 동시에 남는다. requested_format 을 박는 이유는 운영자가
    # .env 에 실제로 박은 값을 보여줘야 진단 가치가 있기 때문 (log_format 변수는
    # 이미 "json" 으로 덮어쓴 상태).
    if forced_json:
        logger.warning(
            "PROD 환경에서 LOG_FORMAT={} 가 지정되어 있어 json 으로 강제 변환했습니다. "
            "Promtail JSON parser 호환 보호.",
            requested_format,
        )

    logger.info("Logging system initialized with level: {}", settings.LOG_LEVEL)


def get_logger(name: str) -> Logger:
    """이름이 지정된 로거 가져오기"""
    return logger.bind(logger_name=name)


# 전역 로거 인스턴스
app_logger = get_logger("app")