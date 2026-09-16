"""Cache expensive ingestion enrichment (embed / summarize) by content fingerprint.

Key identity: enrichment_hash + operation + model + prompt_version.
Never stores prompts or raw article bodies — only vectors / short summaries.
"""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from backend.core.cache_keys import build_cache_key
from backend.core.config import settings
from backend.core.tenant_cache import CacheFailMode, CachePolicy, tenant_cache
from backend.modules.source_ingestion.adapters.base import normalize_title

OWNER_ENRICHMENT = "enrichment"

# Bump these when prompt text or embed input framing changes.
SUMMARIZE_PROMPT_VERSION = "summarize.v1.max_words=60"
EMBED_INPUT_VERSION = "embed.v1.title_nl_body"


def enrichment_content_hash(*, title: str, body: str) -> str:
    """Stable hash of editorial text only (URL-independent for syndication reuse)."""
    digest = hashlib.sha256()
    digest.update(normalize_title(title).encode("utf-8"))
    digest.update(b"\n")
    digest.update((body or "").encode("utf-8"))
    return digest.hexdigest()


def _policy() -> CachePolicy:
    ttl = int(getattr(settings, "LLM_ENRICHMENT_CACHE_TTL_SECONDS", 7 * 24 * 3600))
    return CachePolicy(
        owner=OWNER_ENRICHMENT,
        ttl_seconds=ttl,
        fail_mode=CacheFailMode.OPEN,
        forbid_credentials=True,
        singleflight=True,
        ttl_jitter_seconds=60,
    )


def _identity(*, content_hash: str, operation: str, model: str, prompt_version: str) -> str:
    safe_model = (model or "default").replace(":", "_").replace("/", "_")[:64]
    return f"{operation}:{safe_model}:{prompt_version}:{content_hash}"


def enrichment_cache_key(
    *,
    tenant_id: UUID,
    content_hash: str,
    operation: str,
    model: str,
    prompt_version: str,
) -> str:
    return build_cache_key(
        owner=OWNER_ENRICHMENT,
        identity=_identity(
            content_hash=content_hash,
            operation=operation,
            model=model,
            prompt_version=prompt_version,
        ),
        tenant_id=tenant_id,
    )


async def cached_embedding(
    *,
    tenant_id: UUID,
    title: str,
    body: str,
    model: str,
    factory,
) -> list[float]:
    content_hash = enrichment_content_hash(title=title, body=body)
    key = enrichment_cache_key(
        tenant_id=tenant_id,
        content_hash=content_hash,
        operation="embed",
        model=model,
        prompt_version=EMBED_INPUT_VERSION,
    )

    async def _factory() -> list[float] | None:
        vector = await factory()
        return list(vector) if vector is not None else None

    value = await tenant_cache.get_or_set(key, policy=_policy(), factory=_factory)
    if not isinstance(value, list):
        # Cache miss path with open fail — still run factory once.
        return await factory()
    return [float(x) for x in value]


async def cached_summary(
    *,
    tenant_id: UUID,
    title: str,
    body: str,
    model: str,
    max_words: int,
    factory,
) -> str:
    content_hash = enrichment_content_hash(title=title, body=body)
    prompt_version = SUMMARIZE_PROMPT_VERSION if max_words == 60 else f"summarize.v1.max_words={max_words}"
    key = enrichment_cache_key(
        tenant_id=tenant_id,
        content_hash=content_hash,
        operation="summarize",
        model=model,
        prompt_version=prompt_version,
    )

    async def _factory() -> str | None:
        text = await factory()
        return str(text) if text is not None else None

    value = await tenant_cache.get_or_set(key, policy=_policy(), factory=_factory)
    if not isinstance(value, str) or not value:
        return await factory()
    return value


def enrichment_cache_stats_payload(value: Any) -> dict[str, str]:
    """Tiny helper for tests — never log cached content."""
    if isinstance(value, list):
        return {"type": "embedding", "dims": str(len(value))}
    if isinstance(value, str):
        return {"type": "summary", "chars": str(len(value))}
    return {"type": "unknown"}
