from __future__ import annotations

from functools import cached_property


class SettingsDerivedMixin:
    """Mixin for Settings: declare fields provided by pydantic Settings."""

    DB_POOL_PROCESS_ROLE: str
    DB_POOL_WORKER_SIZE: int
    DB_POOL_SIZE: int
    DB_POOL_WORKER_MAX_OVERFLOW: int
    DB_POOL_MAX_OVERFLOW: int
    DB_POOL_USE_NULL: bool
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    REDIS_URL: str
    CORS_ORIGINS: str
    COOKIE_SAMESITE: str
    ENCRYPTION_KEY: str
    JWT_SECRET: str
    LLM_TASK_MODELS_JSON: str
    LLM_TASK_TIMEOUTS_JSON: str
    TELEGRAM_CALLBACK_SIGNING_SECRET: str
    CSRF_SECRET: str
    EXTERNAL_SECRET_REFERENCES_JSON: str

    @property
    def db_pool_is_worker(self) -> bool:
        return self.DB_POOL_PROCESS_ROLE.strip().lower() == "worker"

    @property
    def effective_db_pool_size(self) -> int:
        return self.DB_POOL_WORKER_SIZE if self.db_pool_is_worker else self.DB_POOL_SIZE

    @property
    def effective_db_pool_max_overflow(self) -> int:
        if self.db_pool_is_worker:
            return self.DB_POOL_WORKER_MAX_OVERFLOW
        return self.DB_POOL_MAX_OVERFLOW

    @property
    def db_pool_max_connections_per_process(self) -> int:
        """Hard ceiling of checked-out connections for this process."""
        if self.DB_POOL_USE_NULL:
            return 1
        return self.effective_db_pool_size + self.effective_db_pool_max_overflow

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
    def llm_task_timeouts(self) -> dict[str, float]:
        import json

        try:
            parsed = json.loads(self.LLM_TASK_TIMEOUTS_JSON or "{}")
        except json.JSONDecodeError:
            return {}

        timeouts: dict[str, float] = {}
        for key, value in parsed.items():
            try:
                timeout = float(value)
            except (TypeError, ValueError):
                continue
            if timeout > 0:
                timeouts[str(key)] = timeout
        return timeouts

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
