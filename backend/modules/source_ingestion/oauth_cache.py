"""OAuth access-token cache with single-flight refresh (Phase 5.6).

Tokens live under OWNER_OAUTH with forbid_credentials=False.
Never log token values.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from backend.core.config import settings
from backend.core.http import request
from backend.core.tenant_cache import (
    OWNER_OAUTH,
    CachePolicy,
    build_cache_key,
    tenant_cache,
)

logger = logging.getLogger(__name__)

_OAUTH_POLICY = CachePolicy(
    owner=OWNER_OAUTH,
    ttl_seconds=3600,
    forbid_credentials=False,
    singleflight=True,
    ttl_jitter_seconds=15,
)


def _token_valid(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    token = payload.get("token")
    if not token:
        return None
    if float(payload.get("exp", 0)) <= time.time():
        return None
    return str(token)


async def get_reddit_client_credentials_token(
    *,
    client_id: str,
    client_secret: str,
    user_agent: str,
) -> str | None:
    """Return a Reddit app-only access token; refresh under distributed single-flight."""
    key = build_cache_key(owner=OWNER_OAUTH, identity=f"reddit:cc:{client_id}", global_scope=True)
    existing = _token_valid(await tenant_cache.get_json(key, policy=_OAUTH_POLICY))
    if existing:
        return existing

    async def _refresh() -> dict[str, Any] | None:
        try:
            response = await request(
                "POST",
                settings.REDDIT_TOKEN_URL,
                provider="ingestion",
                auth=(client_id, client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": user_agent},
            )
            response.raise_for_status()
            payload = response.json()
            token = payload.get("access_token")
            if not token:
                return None
            expires_in = int(payload.get("expires_in") or 3600)
            skew = max(int(settings.CACHE_OAUTH_SKEW_SECONDS), 1)
            ttl = max(expires_in - skew, 30)
            return {"token": token, "exp": time.time() + ttl}
        except Exception as exc:
            logger.info("oauth_reddit_refresh_failed error=%s", type(exc).__name__)
            return None

    filled = await tenant_cache.get_or_set(key, policy=_OAUTH_POLICY, factory=_refresh)
    return _token_valid(filled)
