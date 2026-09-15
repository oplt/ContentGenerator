from __future__ import annotations

import json

from backend.core.tenant_cache import OWNER_INGESTION, CachePolicy, build_cache_key, tenant_cache
from backend.modules.source_ingestion.adapters import (
    FetchedArticle,
    tokenize_for_similarity,
)
from backend.modules.source_ingestion.models import RawArticle, Source
from tenacity import RetryError


def semantic_duplicate(candidate: FetchedArticle, recent_articles: list[RawArticle]) -> RawArticle | None:
    candidate_tokens = tokenize_for_similarity(f"{candidate.title} {candidate.summary or ''}")
    if not candidate_tokens:
        return None
    for existing in recent_articles:
        existing_tokens = tokenize_for_similarity(f"{existing.title} {existing.summary or ''}")
        if not existing_tokens:
            continue
        overlap = len(candidate_tokens & existing_tokens)
        union = len(candidate_tokens | existing_tokens) or 1
        if overlap / union >= 0.88:
            return existing
    return None


async def articles_from_cache(source: Source) -> list[FetchedArticle]:
    key = build_cache_key(
        owner=OWNER_INGESTION,
        tenant_id=source.tenant_id,
        identity=f"source:{source.id}:last_success",
    )
    policy = CachePolicy(
        owner=OWNER_INGESTION,
        ttl_seconds=max(int(source.stale_cache_ttl_seconds or 3600), 60),
    )
    cached = await tenant_cache.get_json(key, policy=policy)
    if cached is None:
        # Dual-read legacy key during rollout.
        from backend.core.cache import redis_client

        legacy = await redis_client.get(f"ingestion:source:{source.id}:last_success")
        if not legacy:
            return []
        cached = json.loads(legacy)
        await tenant_cache.set_json(key, cached, policy=policy)

    articles: list[FetchedArticle] = []
    for item in cached:
        articles.append(
            FetchedArticle(
                url=item["url"],
                canonical_url=item["canonical_url"],
                title=item["title"],
                summary=item.get("summary"),
                body=item.get("body"),
                author=item.get("author"),
                published_at=None,
                metadata=item.get("metadata", {}),
            )
        )
    return articles


async def save_cache(source: Source, articles: list[FetchedArticle]) -> None:
    key = build_cache_key(
        owner=OWNER_INGESTION,
        tenant_id=source.tenant_id,
        identity=f"source:{source.id}:last_success",
    )
    payload = [
        {
            "url": article.url,
            "canonical_url": article.canonical_url,
            "title": article.title,
            "summary": article.summary,
            "body": article.body,
            "author": article.author,
            "metadata": article.metadata,
        }
        for article in articles
    ]
    policy = CachePolicy(
        owner=OWNER_INGESTION,
        ttl_seconds=max(int(source.stale_cache_ttl_seconds or 3600), 60),
    )
    await tenant_cache.set_json(key, payload, policy=policy)
    # Drop legacy unscoped key.
    await tenant_cache.delete(f"ingestion:source:{source.id}:last_success")


def describe_fetch_error(exc: Exception) -> str:
    if isinstance(exc, RetryError):
        last_error = exc.last_attempt.exception()
        if last_error:
            return str(last_error)
    return str(exc)
