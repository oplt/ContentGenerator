from functools import cached_property
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,
    )

    APP_NAME: str = "SignalForge"
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"
    SQL_ECHO: bool = False
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:4173"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/content_generator"
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_TASK_ALWAYS_EAGER: bool = False
    CELERY_RESULT_EXPIRES_SECONDS: int = 3600
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    CELERY_EMAIL_QUEUE: str = "email_queue"  # Add this line
    CELERY_DEFAULT_QUEUE: str = "default"

    CELERY_QUEUE_INGESTION: str = "ingestion"
    CELERY_QUEUE_ENRICHMENT: str = "enrichment"
    CELERY_QUEUE_GENERATION: str = "generation"
    CELERY_QUEUE_VIDEO: str = "video"
    CELERY_QUEUE_APPROVALS: str = "approvals"
    CELERY_QUEUE_PUBLISHING: str = "publishing"
    CELERY_QUEUE_ANALYTICS: str = "analytics"
    CELERY_QUEUE_EMAIL: str = "email"

    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    COOKIE_SECURE: bool = False
    FRONTEND_URL: str = "http://localhost:5173"
    ADMIN_SIGNUP_INVITE_CODE: str = ""

    VERIFICATION_TOKEN_TTL: int = 86400
    PASSWORD_RESET_TOKEN_TTL: int = 3600
    RATE_LIMIT_DEFAULT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_DEFAULT_MAX_ATTEMPTS: int = 60

    ENCRYPTION_KEY: str = ""

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@example.com"
    SMTP_TLS: bool = True

    STORAGE_BUCKET: str = "content-generator"
    STORAGE_REGION: str = "us-east-1"
    STORAGE_ENDPOINT_URL: str = "http://localhost:9000"
    STORAGE_ACCESS_KEY: str = "minioadmin"
    STORAGE_SECRET_KEY: str = "minioadmin"
    STORAGE_USE_SSL: bool = False
    STORAGE_FORCE_PATH_STYLE: bool = True
    STORAGE_PUBLIC_BASE_URL: str = "http://localhost:9000/content-generator"
    STORAGE_AUTO_CREATE_BUCKET: bool = True
    STORAGE_PUBLIC_READ: bool = True
    STORAGE_SIGNED_URL_EXPIRES_SECONDS: int = 900

    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    OTLP_ENDPOINT: str = ""
    OTLP_INSECURE: bool = True
    OTEL_SERVICE_NAME: str = "content-generator-api"

    HTTP_TIMEOUT_SECONDS: float = 20.0
    HTTP_MAX_RETRIES: int = 3
    INGESTION_STALE_CACHE_TTL_SECONDS: int = 3600
    INGESTION_NEGATIVE_CACHE_TTL_SECONDS: int = 900
    INGESTION_DEFAULT_POLL_MINUTES: int = 30

    LLM_PROVIDER: str = "mock"
    LLM_MODEL: str = "mock-gpt"
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    EMBEDDINGS_PROVIDER: str = "hashing"
    EMBEDDINGS_MODEL: str = "hashing-v1"
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    TTS_PROVIDER: str = "mock"
    VISUAL_PROVIDER: str = "mock"
    CAPTION_PROVIDER: str = "mock"
    FFMPEG_BIN: str = "ffmpeg"
    FFPROBE_BIN: str = "ffprobe"

    WHATSAPP_PROVIDER: str = "stub"
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "dev-verify-token"
    WHATSAPP_APP_SECRET: str = ""
    WHATSAPP_DEFAULT_RECIPIENT: str = "+10000000000"

    SOCIAL_DRY_RUN_BY_DEFAULT: bool = True
    X_API_BASE_URL: str = "https://api.x.com"
    BLUESKY_PDS_URL: str = "https://bsky.social"
    YOUTUBE_API_BASE_URL: str = "https://www.googleapis.com"
    INSTAGRAM_GRAPH_BASE_URL: str = "https://graph.facebook.com"
    TIKTOK_API_BASE_URL: str = "https://open.tiktokapis.com"

    DEMO_TENANT_SLUG: str = "demo-agency"
    DEMO_ADMIN_EMAIL: str = "demo@example.com"
    DEMO_ADMIN_PASSWORD: str = "password1234"
    DEMO_ADMIN_NAME: str = "Demo Operator"
    DEMO_SEED_ENABLED: bool = True

    @property
    def celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def celery_result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    @cached_property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @cached_property
    def encryption_key(self) -> bytes:
        if self.ENCRYPTION_KEY:
            return self.ENCRYPTION_KEY.encode("utf-8")
        from base64 import urlsafe_b64encode
        import hashlib

        digest = hashlib.sha256(self.JWT_SECRET.encode("utf-8")).digest()
        return urlsafe_b64encode(digest)


settings = Settings()
