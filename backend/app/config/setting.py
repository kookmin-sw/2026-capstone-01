from typing import Literal, Optional
import socket
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """애플리케이션 설정"""
    
    # 서버
    HOST: str = Field("0.0.0.0", description="서버 호스트")
    PORT: int = Field(8000, description="서버 포트 번호") 
    
    # CORS 프론트 설정
    FRONTEND_URL: str = Field("https://krip.site", description="서버 프론트 URL")
    LOCAL_FRONTEND_URL: str = Field("https://localhost:3000", description="로컬 프론트 URL")

    # 환경
    ENVIRONMENT: str = Field("DEV", description="환경 (실서버, 개발서버)")
    
    # 로깅 설정
    LOG_LEVEL: str = Field("INFO", description="로그 레벨")
    LOG_FORMAT: str = Field("console", description="로그 포맷 (json/console)")
    LOG_FILE_PATH: Optional[str] = Field(
        "/backend/logs/app.log",
        description=".env 누락 시에도 Promtail 이 정상 tail 하도록 default 명시. "
                    "console 출력만 원하면 .env 에서 LOG_FILE_PATH= 빈 값으로 override.",
    )
    LOG_ROTATION: str = Field("100 MB", description="로그 로테이션")
    LOG_RETENTION: str = Field("30 days", description="로그 보관 기준")
    LOG_COMPRESSION: str = Field("gz", description="로그 롤테이션 파일 압축")
    
    # POSTGRES 정보
    POSTGRES_HOST: str = Field("hyeonsang-postgres", description="POSTGRES HOST")
    POSTGRES_PORT: int = Field(5432, description="POSTGRES PORT")
    POSTGRES_USER: str = Field("cho", description="POSTGRES USER")
    POSTGRES_PASSWORD: str = Field("hyeonsang", description="POSTGRES PASSWORD")
    POSTGRES_NAME: str = Field("chohyeonsang", description="POSTGRES NAME")
    
    # MongoDB 정보
    MONGODB_HOST: str = Field("hyeonsang-mongodb", description="MONGODB HOST")
    MONGODB_PORT: int = Field(27017, description="MONGODB PORT")
    MONGODB_USER: str = Field("cho", description="MONGODB USER")
    MONGODB_PASSWORD: str = Field("hyeonsang", description="MONGODB PASSWORD")
    MONGODB_NAME: str = Field("chohyeonsang", description="MONGODB NAME")
    
    # Redis 정보
    REDIS_HOST: str = Field("hyeonsang-redis", description="REDIS HOST")
    REDIS_PORT: int = Field(6379, description="REDIS PORT")
    REDIS_DB: int = Field(0, description="REDIS DB — 세션/시퀀스/unread 등 핫 데이터")
    REDIS_DB_DEDUPE: int = Field(1, description="REDIS DB — dedupe 키 전용 격리 (KEYS 사고 방지)")

    # WebSocket / 채팅 fan-out 설정
    FANOUT_MODE: Literal["in_process", "node_channel"] = Field(
        "in_process",
        description="채팅 fan-out 모드.",
    )
    NODE_ID: str = Field(
        default_factory=socket.gethostname,
        description="노드 식별자. 기본값은 hostname(k8s pod name).",
    )

    # 모니터링
    METRICS_PORT: int = Field(
        9090,
        description="prometheus_client /metrics 노출 포트. backend 8000 과 분리되어 self-noise 차단"
                    "k8s 진입 시 9090 은 NetworkPolicy 로 monitoring namespace 만 도달.",
    )

    # 인증 정보
    ACCESS_TOKEN: str = Field(..., description="API 접근 토큰")
    
    # USER LOGIN JWT 설정
    USER_LOGIN_JWT_SECRET_KEY: str = Field("your-secret-key-here", description="USER LOGIN JWT 비밀키")
    USER_LOGIN_JWT_ALGORITHM: str = Field("HS256", description="USER LOGIN JWT 알고리즘")
    USER_LOGIN_JWT_EXPIRATION_DAYS: int = Field(1, description="USER LOGIN JWT 토큰 만료 기간 (일)")
    USER_LOGIN_COOKIE_NAME: str = Field("utk", description="USER LOGIN 쿠키명")
    
    # 공유 JWT 설정
    SHARE_JWT_SECRET_KEY: str = Field("your-share-secret-here", description="플랜 share JWT 비밀키")
    SHARE_JWT_ALGORITHM: str = Field("HS256", description="플랜 share JWT 알고리즘")
    SHARE_JWT_EXPIRATION_DAYS: int = Field(30, description="플랜 share 토큰 만료 기간 (일)")
    
    # Google OAuth
    GOOGLE_CLIENT_ID: str = Field(..., description="구글 OAuth ID")
    GOOGLE_CLIENT_SECRET: str = Field(..., description="구글 OAuth Secret")
    
    # OAuth Redirect Base URL
    OAUTH_REDIRECT_BASE_URL: str = Field(..., description="OAuth Redirect URL")
    
    # NaverCloud S3 Object Storage 설정
    S3_ACCESS_KEY_ID: str = Field(..., description="Object Storage S3_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY: str = Field(..., description="Object Storage S3_SECRET_ACCESS_KEY")
    S3_REGION: str = Field(..., description="Object Storage S3_REGION")
    S3_BUCKET_NAME: str = Field(..., description="Object Storage S3_BUCKET_NAME")
    S3_ENDPOINT_URL: str = Field(..., description="Object Storage S3_ENDPOINT_URL")
    
    # LLM
    GOOGLE_GEMINI_API_KEY: str = Field(..., description="구글 제미나이 API 키")

    # Papago (Naver Developers — 번역/언어 감지)
    PAPAGO_CLIENT_ID: str = Field(..., description="Papago Client ID")
    PAPAGO_CLIENT_SECRET: str = Field(..., description="Papago Client Secret")

    # FCM (Firebase Cloud Messaging)
    FCM_CREDENTIALS_PATH: str = Field(
        "secrets/krip-firebase-secret-key.json",
        description="Firebase Admin SDK 서비스 계정 JSON 경로 (backend/ 기준 상대 또는 절대)",
    )
    
    @property
    def POSTGRES_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_NAME}"
    
    @property
    def SYNC_POSTGRES_URL(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_NAME}"
    
    @property
    def MONGODB_URL(self) -> str:
        return f"mongodb://{self.MONGODB_USER}:{self.MONGODB_PASSWORD}@{self.MONGODB_HOST}:{self.MONGODB_PORT}/{self.MONGODB_NAME}?authSource=admin"
    
    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def REDIS_URL_DEDUPE(self) -> str:
        """dedupe 키 전용 Redis URL. DB 번호만 분리하여 운영자의 `KEYS dedupe:*` 실수가
        세션/시퀀스 등 핫 데이터에 영향을 주지 않도록 격리한다."""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB_DEDUPE}"
    
    @property
    def is_production(self) -> bool:
        """프로덕션 환경 여부"""
        return self.ENVIRONMENT == "PROD"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # .env / shell 의 미선언 변수 (LANGCHAIN_* 등) 허용
    )


settings = Settings()