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
    COOKIE_SAMESITE: str = "lax"
    FRONTEND_URL: str = "http://localhost:5173"
    ADMIN_SIGNUP_INVITE_CODE: str = ""
    SEND_AUTH_EMAIL_ON_SIGNUP: bool = False

    VERIFICATION_TOKEN_TTL: int = 86400
    PASSWORD_RESET_TOKEN_TTL: int = 3600
    RATE_LIMIT_DEFAULT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_DEFAULT_MAX_ATTEMPTS: int = 60
    AUTH_FAILURE_LOCK_THRESHOLD: int = 5
    AUTH_FAILURE_WINDOW_SECONDS: int = 900
    AUTH_LOCKOUT_SECONDS: int = 900

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
    INGESTION_DISABLE_AFTER_FAILURES: int = 5
    ENABLE_X_SIGNAL_CONNECTOR: bool = False
    ENABLE_BLUESKY_SIGNAL_CONNECTOR: bool = False
    ENABLE_GOOGLE_TRENDS_CONNECTOR: bool = False
    ENABLE_OFFICIAL_SOURCE_CONNECTOR: bool = True
    GOOGLE_TRENDS_REGION: str = "US"
    GOOGLE_TRENDS_RSS_URL: str = "https://trends.google.com/trending/rss"
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "content-generator/1.0"
    REDDIT_USERNAME: str = ""
    REDDIT_PASSWORD: str = ""
    REDDIT_API_BASE_URL: str = "https://oauth.reddit.com"
    REDDIT_TOKEN_URL: str = "https://www.reddit.com/api/v1/access_token"
    BLUESKY_HANDLE: str = ""
    BLUESKY_APP_PASSWORD: str = ""

    # LLM provider: "mock" (default/tests), "ollama", "vllm", "llamacpp", "openai_compatible"
    # Override in .env or docker-compose environment section for real deployments.
    LLM_PROVIDER: str = "mock"
    LLM_MODEL: str = "llama3.2:3b"
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_TIMEOUT_SECONDS: float = 45.0
    LLM_MAX_RETRIES: int = 2
    LLM_JSON_ENFORCEMENT: str = "best_effort"
    LLM_FALLBACK_ORDER: str = "ollama,vllm,llamacpp,openai_compatible,mock"
    LLM_TASK_MODELS_JSON: str = "{}"
    LLM_TASK_PROVIDER_OVERRIDES_JSON: str = "{}"
    LLM_TASK_REQUIREMENTS_JSON: str = "{}"
    LLM_PROVIDER_CAPABILITIES_JSON: str = "{}"
    VLLM_BASE_URL: str = "http://localhost:8001/v1"
    LLAMACPP_BASE_URL: str = "http://localhost:8080/v1"
    # Embedding provider: "hashing" (tests/mock), "ollama" (local), "openai_compatible" (API)
    # Override to "ollama" with EMBEDDINGS_MODEL=nomic-embed-text in docker-compose.
    EMBEDDINGS_PROVIDER: str = "hashing"
    EMBEDDINGS_MODEL: str = "nomic-embed-text"
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # TTS: "mock" | "piper" (local binary) | "kokoro" (local HTTP) | "openai" | "elevenlabs"
    TTS_PROVIDER: str = "mock"
    TTS_PIPER_BIN: str = "piper"
    TTS_PIPER_MODEL: str = ""           # path to .onnx model file
    TTS_PIPER_SAMPLE_RATE: int = 22050
    TTS_KOKORO_BASE_URL: str = "http://localhost:8880"
    TTS_KOKORO_VOICE: str = "af_sky"
    TTS_OPENAI_API_KEY: str = ""
    TTS_OPENAI_MODEL: str = "tts-1"
    TTS_OPENAI_VOICE: str = "alloy"
    TTS_ELEVENLABS_API_KEY: str = ""
    TTS_ELEVENLABS_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"
    TTS_ELEVENLABS_MODEL_ID: str = "eleven_monolingual_v1"
    VISUAL_PROVIDER: str = "mock"
    CAPTION_PROVIDER: str = "mock"

    # Image generation: "mock" | "stable_diffusion" (local A1111) | "openai" (DALL-E)
    IMAGE_PROVIDER: str = "mock"
    IMAGE_SD_BASE_URL: str = "http://localhost:7860"  # AUTOMATIC1111 endpoint
    IMAGE_SD_STEPS: int = 20
    IMAGE_SD_CFG_SCALE: float = 7.0
    IMAGE_OPENAI_API_KEY: str = ""
    IMAGE_OPENAI_MODEL: str = "dall-e-3"
    IMAGE_GENERATION_WIDTH: int = 1024
    IMAGE_GENERATION_HEIGHT: int = 1024
    FFMPEG_BIN: str = "ffmpeg"
    FFPROBE_BIN: str = "ffprobe"

    TELEGRAM_WEBHOOK_SECRET: str = ""
    TELEGRAM_CALLBACK_SIGNING_SECRET: str = ""
    CSRF_SECRET: str = ""
    EXTERNAL_SECRET_REFERENCES_JSON: str = "{}"

    GITHUB_TOKEN: str = ""

    WHATSAPP_PROVIDER: str = "stub"
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "dev-verify-token"
    WHATSAPP_APP_SECRET: str = ""
    WHATSAPP_DEFAULT_RECIPIENT: str = "+10000000000"

    SOCIAL_DRY_RUN_BY_DEFAULT: bool = True
    X_API_BASE_URL: str = "https://api.x.com"
    X_UPLOAD_BASE_URL: str = "https://upload.twitter.com"
    BLUESKY_PDS_URL: str = "https://bsky.social"
    YOUTUBE_API_BASE_URL: str = "https://www.googleapis.com"
    INSTAGRAM_GRAPH_BASE_URL: str = "https://graph.facebook.com"
    TIKTOK_API_BASE_URL: str = "https://open.tiktokapis.com"
    ANALYTICS_SYNTHETIC_MODE: bool = False
    PUBLIC_URL: str

    DEMO_TENANT_SLUG: str = "demo-agency"
    DEMO_ADMIN_EMAIL: str = "demo@example.com"
    DEMO_ADMIN_PASSWORD: str = "password1234"
    DEMO_ADMIN_NAME: str = "Demo Operator"
    DEMO_SEED_ENABLED: bool = True

    MFA_ACCESS: bool = False

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
    def cookie_samesite(self) -> str:
        normalized = self.COOKIE_SAMESITE.strip().lower()
        if normalized not in {"lax", "strict", "none"}:
            return "lax"
        return normalized

    @cached_property
    def encryption_key(self) -> bytes:
        if self.ENCRYPTION_KEY:
            return self.ENCRYPTION_KEY.encode("utf-8")
        from base64 import urlsafe_b64encode
        import hashlib

        digest = hashlib.sha256(self.JWT_SECRET.encode("utf-8")).digest()
        return urlsafe_b64encode(digest)

    @cached_property
    def llm_task_models(self) -> dict[str, str]:
        import json

        try:
            parsed = json.loads(self.LLM_TASK_MODELS_JSON or "{}")
        except json.JSONDecodeError:
            return {}
        return {str(key): str(value) for key, value in parsed.items() if key and value}

    @cached_property
    def llm_fallback_order(self) -> list[str]:
        return [item.strip().lower() for item in self.LLM_FALLBACK_ORDER.split(",") if item.strip()]

    @cached_property
    def telegram_callback_signing_secret(self) -> str:
        return self.TELEGRAM_CALLBACK_SIGNING_SECRET or self.JWT_SECRET

    @cached_property
    def csrf_secret(self) -> str:
        return self.CSRF_SECRET or self.JWT_SECRET

    @cached_property
    def external_secret_references(self) -> dict[str, str]:
        import json

        try:
            parsed = json.loads(self.EXTERNAL_SECRET_REFERENCES_JSON or "{}")
        except json.JSONDecodeError:
            return {}
        return {str(key): str(value) for key, value in parsed.items() if key and value}


settings = Settings()
