"""Cache key builders and owner constants."""

from __future__ import annotations

from uuid import UUID

from backend.core.config import settings

OWNER_CONTENT_STRATEGY = "content_strategy"
OWNER_IDENTITY = "identity"
OWNER_INGESTION = "ingestion"
OWNER_ENRICHMENT = "enrichment"
OWNER_AUTH_TOKEN = "auth_token"
OWNER_ROBOTS = "robots"
OWNER_OAUTH = "oauth"
OWNER_CHESS = "chess_intelligence"


def cache_env() -> str:
    return (settings.APP_ENV or "development").strip().lower() or "development"


def build_cache_key(
    *,
    owner: str,
    identity: str,
    tenant_id: UUID | str | None = None,
    global_scope: bool = False,
    version: str | None = None,
) -> str:
    if not owner or ":" in owner or "/" in owner:
        raise ValueError("owner must be a non-empty token without ':' or '/'")
    if not identity:
        raise ValueError("identity must be non-empty")
    if global_scope:
        scope = "global"
    else:
        if tenant_id is None:
            raise ValueError("tenant_id required unless global_scope=True")
        scope = str(tenant_id)
    key = f"cg:{cache_env()}:{scope}:{owner}:{identity}"
    if version:
        key = f"{key}:v{version}"
    return key
