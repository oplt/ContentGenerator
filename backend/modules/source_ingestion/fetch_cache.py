from __future__ import annotations

import json
from collections.abc import Sequence

from backend.core.tenant_cache import OWNER_INGESTION, CachePolicy, build_cache_key, tenant_cache
from backend.modules.source_ingestion.adapters import (
    FetchedArticle,
    tokenize_for_similarity,
)
from backend.modules.source_ingestion.models import RawArticle, Source
from tenacity import RetryError

ArticleTokenIndex = list[tuple[RawArticle, frozenset[str]]]


def build_article_token_index(articles: Sequence[RawArticle]) -> ArticleTokenIndex:
    """Tokenize each article once for batch semantic comparison."""
    index: ArticleTokenIndex = []
    for article in articles:
        tokens = frozenset(tokenize_for_similarity(f"{article.title} {article.summary or ''}"))
        if tokens:
            index.append((article, tokens))
    return index


def semantic_duplicate(
    candidate: FetchedArticle,
    recent_articles: Sequence[RawArticle] | None = None,
    *,
    token_index: ArticleTokenIndex | None = None,
) -> RawArticle | None:
    """
    Jaccard similarity against recent articles.

    Prefer passing ``token_index`` from ``build_article_token_index`` when comparing
    many candidates against the same recent set (avoids O(n*m) re-tokenization).
    """
    candidate_tokens = tokenize_for_similarity(f"{candidate.title} {candidate.summary or ''}")
    if not candidate_tokens:
        return None
    indexed = token_index if token_index is not None else build_article_token_index(recent_articles or [])
    for existing, existing_tokens in indexed:
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
