from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.core.settings_derived import SettingsDerivedMixin


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(SettingsDerivedMixin, BaseSettings):
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
    SQL_SLOW_QUERY_MS: float = Field(default=500.0, ge=1.0)
    HEALTH_CHECK_TIMEOUT_SECONDS: float = Field(default=0.75, gt=0, le=5)
    # Refuse API/worker/beat startup and readiness when alembic_version != head.
    SCHEMA_REVISION_ENFORCE: bool = True
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:4173"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/content_generator"
    # Bounded async pool (API/workers). Totals must stay under PostgreSQL max_connections:
    #   processes * (DB_POOL_SIZE + DB_POOL_MAX_OVERFLOW) < max_connections - reserve
    # Set DB_POOL_USE_NULL=true for alembic/one-shot scripts that must not hold pooled conns.
    DB_POOL_USE_NULL: bool = False
    DB_POOL_SIZE: int = Field(default=5, ge=1, le=100)
    DB_POOL_MAX_OVERFLOW: int = Field(default=10, ge=0, le=100)
    DB_POOL_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0)
    DB_POOL_RECYCLE_SECONDS: int = Field(default=1800, ge=0)
    # api|worker — selects documented defaults via effective_* helpers; override sizes with env.
    DB_POOL_PROCESS_ROLE: str = "api"
    DB_POOL_WORKER_SIZE: int = Field(default=2, ge=1, le=50)
    DB_POOL_WORKER_MAX_OVERFLOW: int = Field(default=2, ge=0, le=50)
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
    # Global worker execution policy (per-task soft/hard limits live in task_policy.py).
    CELERY_WORKER_PREFETCH_MULTIPLIER: int = Field(default=1, ge=1, le=16)
    CELERY_TASK_REJECT_ON_WORKER_LOST: bool = True
    CELERY_TASK_ACKS_LATE_DEFAULT: bool = False
    CELERY_TASK_DEFAULT_SOFT_TIME_LIMIT: int = Field(default=300, ge=10)
    CELERY_TASK_DEFAULT_TIME_LIMIT: int = Field(default=360, ge=15)
    CELERY_WORKER_IO_CONCURRENCY: int = Field(default=4, ge=1, le=32)
    CELERY_WORKER_LLM_CONCURRENCY: int = Field(default=2, ge=1, le=16)
    CELERY_WORKER_MEDIA_CONCURRENCY: int = Field(default=1, ge=1, le=8)
    CELERY_WORKER_PUBLISHING_CONCURRENCY: int = Field(default=2, ge=1, le=16)
    # Analytics / bulk persistence — keep ≤ worker DB pool slots.
    CELERY_WORKER_DB_CONCURRENCY: int = Field(default=2, ge=1, le=16)

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
    # "s3" talks to MinIO/S3; "local" writes under STORAGE_LOCAL_ROOT and serves via /api/v1/media.
    STORAGE_BACKEND: str = "s3"
    STORAGE_LOCAL_ROOT: str = ""

    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    OTLP_ENDPOINT: str = ""
    OTLP_INSECURE: bool = True
    OTEL_SERVICE_NAME: str = "content-generator-api"

    HTTP_TIMEOUT_SECONDS: float = 20.0
    HTTP_MAX_RETRIES: int = 3
    HTTP_CONNECT_TIMEOUT_SECONDS: float = 5.0
    HTTP_READ_TIMEOUT_SECONDS: float = 20.0
    HTTP_WRITE_TIMEOUT_SECONDS: float = 20.0
    HTTP_POOL_TIMEOUT_SECONDS: float = 5.0
    HTTP_MAX_CONNECTIONS: int = 100
    HTTP_MAX_KEEPALIVE_CONNECTIONS: int = 20
    HTTP_PROVIDER_MAX_CONCURRENCY: int = 8
    HTTP_PROVIDER_GITHUB_CONCURRENCY: int = 4
    HTTP_PROVIDER_ANALYTICS_CONCURRENCY: int = 6
    HTTP_PROVIDER_X_CONCURRENCY: int = 4
    HTTP_PROVIDER_LLM_CONCURRENCY: int = 1
    HTTP_PROVIDER_INGESTION_CONCURRENCY: int = 8
    HTTP_PROVIDER_PUBLISHING_CONCURRENCY: int = 4
    HTTP_PROVIDER_IMAGE_CONCURRENCY: int = 2
    HTTP_PROVIDER_TTS_CONCURRENCY: int = 2
    HTTP_PROVIDER_LICHESS_CONCURRENCY: int = 2
    HTTP_PROVIDER_CHESSCOM_CONCURRENCY: int = 2
    HTTP_RETRY_AFTER_MAX_SECONDS: float = 60.0
    HTTP_INGESTION_HEALTH_CONCURRENCY: int = 8
    HTTP_INGESTION_ENRICH_CONCURRENCY: int = 6
    HTTP_SITEMAP_GLOBAL_CONCURRENCY: int = 4
    HTTP_SITEMAP_PER_ORIGIN_CONCURRENCY: int = 2
    HTTP_SITEMAP_DEFAULT_TIMEOUT_SECONDS: float = 60.0
    HTTP_SITEMAP_DEFAULT_MAX_URLS: int = 500
    CACHE_SINGLEFLIGHT_LOCK_MS: int = 15_000
    CACHE_DEFAULT_TTL_JITTER_SECONDS: int = 30
    CACHE_ROBOTS_TTL_SECONDS: int = 3600
    # Cached embed/summarize results for unchanged article text (Phase 12).
    LLM_ENRICHMENT_CACHE_TTL_SECONDS: int = Field(default=604_800, ge=60, le=30 * 24 * 3600)
    CACHE_OAUTH_SKEW_SECONDS: int = 60
    # Optional dedicated app-cache Redis URL (else REDIS_URL). Prefer isolating
    # cache vs Celery broker/results in production.
    REDIS_CACHE_URL: str = ""
    PUBLISHING_CLAIM_LEASE_SECONDS: int = 900
    PUBLISHING_MAX_ATTEMPTS: int = 3
    PUBLISHING_CLAIM_BATCH_SIZE: int = 50
    # Workflow node claim lease (Phase 1 durable execution).
    WORKFLOW_CLAIM_LEASE_SECONDS: int = Field(default=900, ge=60, le=86_400)
    WORKFLOW_CLAIM_RECOVERY_BATCH_SIZE: int = Field(default=50, ge=1, le=500)
    # When True, advance executes claimed nodes in-process (unit tests / local sync).
    # Production must keep this False so API/workers only enqueue Celery node tasks.
    WORKFLOW_INLINE_NODE_EXECUTION: bool = False
    # Phase 20 — historical payload retention (scrub/delete; never blind-delete audit_logs).
    WORKFLOW_RETENTION_ENABLED: bool = True
    WORKFLOW_RETENTION_NODE_PAYLOAD_DAYS: int = Field(default=30, ge=1, le=3650)
    WORKFLOW_RETENTION_TASK_EXECUTION_DAYS: int = Field(default=14, ge=1, le=3650)
    WORKFLOW_RETENTION_WEBHOOK_PAYLOAD_DAYS: int = Field(default=14, ge=1, le=3650)
    WORKFLOW_RETENTION_BATCH_SIZE: int = Field(default=200, ge=1, le=5_000)
    # When True and object storage is configured, archive payloads to S3/MinIO before scrub.
    WORKFLOW_RETENTION_ARCHIVE_TO_STORAGE: bool = False
    PUBLISHING_ACCOUNT_MAX_PUBLISHES_PER_HOUR: int = Field(default=30, ge=1, le=10_000)
    PUBLISHING_ACCOUNT_MAX_RETRIES_PER_HOUR: int = Field(default=10, ge=1, le=10_000)
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
    LLM_PROVIDER: str = "ollama"
    LLM_MODEL: str = "llama3.2:3b"
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_TIMEOUT_SECONDS: float = 45.0
    LLM_MAX_RETRIES: int = 2
    LLM_JSON_ENFORCEMENT: str = "best_effort"
    LLM_TASK_MODELS_JSON: str = "{}"
    LLM_TASK_TIMEOUTS_JSON: str = "{}"
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

    # Lichess opening explorer (masters / puzzles). Token optional but may be required
    # for /masters search depending on upstream policy; never expose to frontend.
    LICHESS_API_TOKEN: str = ""
    LICHESS_API_BASE_URL: str = "https://lichess.org"
    LICHESS_EXPLORER_BASE_URL: str = "https://explorer.lichess.org"
    LICHESS_HTTP_TIMEOUT_SECONDS: float = Field(default=20.0, gt=0, le=120)
    LICHESS_RATE_LIMIT_RPH: int = Field(default=60, ge=1, le=3600)
    LICHESS_HTTP_MAX_RETRIES: int = Field(default=2, ge=0, le=5)

    # Chess provider response cache (TenantCache / Redis) — Phase 22
    CHESS_CACHE_MASTERS_SEARCH_TTL_SECONDS: int = Field(default=1800, ge=60, le=86_400)
    CHESS_CACHE_GAME_PGN_TTL_SECONDS: int = Field(default=604_800, ge=300, le=30 * 24 * 3600)
    CHESS_CACHE_PUZZLE_TTL_SECONDS: int = Field(default=604_800, ge=300, le=30 * 24 * 3600)
    CHESS_CACHE_PROVIDER_META_TTL_SECONDS: int = Field(default=3600, ge=60, le=86_400)
    # Daily puzzle: soft ceiling; runtime also clamps to next UTC midnight.
    CHESS_CACHE_DAILY_PUZZLE_TTL_SECONDS: int = Field(default=21_600, ge=300, le=86_400)

    # Chess.com PubAPI (no auth). Identify via User-Agent; fair-use rate limit.
    CHESSCOM_API_BASE_URL: str = "https://api.chess.com"
    CHESSCOM_USER_AGENT: str = "SignalForgeChessIntelligence/1.0 (contact: ops@localhost)"
    CHESSCOM_HTTP_TIMEOUT_SECONDS: float = Field(default=20.0, gt=0, le=120)
    CHESSCOM_RATE_LIMIT_RPH: int = Field(default=60, ge=1, le=3600)
    CHESSCOM_HTTP_MAX_RETRIES: int = Field(default=2, ge=0, le=5)

    # Stockfish binary (external executable). Empty → analysis endpoints return 503.
    STOCKFISH_PATH: str = ""
    CHESS_ENGINE_DEPTH: int | None = Field(default=12, ge=1, le=40)
    CHESS_ENGINE_TIME_LIMIT: float | None = Field(default=None, gt=0, le=60)
    CHESS_ENGINE_HASH_MB: int = Field(default=64, ge=1, le=4096)
    CHESS_ENGINE_THREADS: int = Field(default=1, ge=1, le=32)

    WHATSAPP_PROVIDER: str = "stub"
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "dev-verify-token"
    WHATSAPP_APP_SECRET: str = ""
    WHATSAPP_DEFAULT_RECIPIENT: str = "+10000000000"

    SOCIAL_DRY_RUN_BY_DEFAULT: bool = True
    # Multi-account staged rollout: off | shadow | canary | on (default on = shipped T4).
    MULTI_ACCOUNT_ROLLOUT_MODE: str = "on"
    MULTI_ACCOUNT_CANARY_PERCENT: int = Field(default=0, ge=0, le=100)
    # Comma-separated tenant UUIDs always included in canary.
    MULTI_ACCOUNT_CANARY_TENANT_IDS: str = ""
    X_API_BASE_URL: str = "https://api.x.com"
    X_UPLOAD_BASE_URL: str = "https://upload.twitter.com"
    BLUESKY_PDS_URL: str = "https://bsky.social"
    YOUTUBE_API_BASE_URL: str = "https://www.googleapis.com"
    INSTAGRAM_GRAPH_BASE_URL: str = "https://graph.facebook.com"
    TIKTOK_API_BASE_URL: str = "https://open.tiktokapis.com"
    ANALYTICS_SYNTHETIC_MODE: bool = False
    PUBLIC_URL: str = "http://localhost:5173"

    DEMO_TENANT_SLUG: str = "demo-agency"
    DEMO_ADMIN_EMAIL: str = "demo@example.com"
    DEMO_ADMIN_PASSWORD: str = "password1234"
    DEMO_ADMIN_NAME: str = "Demo Operator"
    DEMO_SEED_ENABLED: bool = True

    MFA_ACCESS: bool = False


settings = Settings()
