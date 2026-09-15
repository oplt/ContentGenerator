from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from backend.core.config import settings
from backend.core.http import request
from backend.modules.source_ingestion.models import Source


_TITLE_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_TITLE_MULTI_SPACE = re.compile(r"\s+")


def normalize_title(value: str) -> str:
    cleaned = _TITLE_NON_ALNUM.sub(" ", (value or "").lower()).strip()
    return _TITLE_MULTI_SPACE.sub(" ", cleaned)


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
    ]
    normalized_path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            normalized_path,
            "",
            urlencode(sorted(query_items)),
            "",
        )
    )


def tokenize_for_similarity(text: str) -> set[str]:
    return {token for token in normalize_title(text).split() if len(token) > 2}


@dataclass
class FetchedArticle:
    url: str
    canonical_url: str
    title: str
    summary: str | None
    body: str | None
    author: str | None
    published_at: datetime | None
    metadata: dict[str, str]
    language: str | None = None
    category_tags: list[str] = field(default_factory=list)
    region_tags: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)
    external_id: str | None = None
    parser_diagnostics: dict[str, str] = field(default_factory=dict)

    @property
    def title_normalized(self) -> str:
        return normalize_title(self.title)

    @property
    def content_hash(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.canonical_url.encode("utf-8"))
        digest.update((self.title_normalized or "").encode("utf-8"))
        digest.update((self.body or self.summary or "").encode("utf-8"))
        return digest.hexdigest()


class BaseSourceAdapter:
    connector_name = "base"

    def __init__(self, source: Source):
        self.source = source

    async def _fetch_text(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        auth: tuple[str, str] | None = None,
        data: dict[str, str] | None = None,
        method: str = "GET",
    ) -> str:
        response = await request(
            method,
            url,
            provider="ingestion",
            headers=headers or {"User-Agent": settings.APP_NAME},
            auth=auth,
            data=data,
        )
        response.raise_for_status()
        return response.text

    async def _fetch_json(self, url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        raw = await self._fetch_text(url, headers=headers)
        return cast(dict[str, Any], json.loads(raw))

    async def _robots_allowed(self, url: str) -> bool:
        # Per-adapter memo so one fetch chain does not re-check the same origin.
        cache = getattr(self, "_robots_decision_cache", None)
        if cache is None:
            cache = {}
            self._robots_decision_cache = cache
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}".lower()
        if origin in cache:
            return cache[origin]
        from backend.modules.source_ingestion.robots_cache import robots_allowed

        allowed = await robots_allowed(
            url,
            user_agent=settings.APP_NAME,
            respected=self.source.robots_respected,
        )
        cache[origin] = allowed
        return allowed

    async def fetch(self) -> list[FetchedArticle]:
        raise NotImplementedError

    async def normalize(self, articles: list[FetchedArticle]) -> list[FetchedArticle]:
        normalized: list[FetchedArticle] = []
        seen: set[str] = set()
        for article in articles:
            article.canonical_url = canonicalize_url(article.canonical_url or article.url)
            article.metadata = {
                **article.metadata,
                "connector": self.connector_name,
                "source_name": self.source.name,
                "source_type": str(self.source.source_type),
                "source_tier": self.source.source_tier,
            }
            if not article.category_tags:
                article.category_tags = list(self.source.category_tags or [self.source.category])
            if not article.region_tags:
                article.region_tags = list(self.source.region_tags or [])
            dedupe_key = self.dedupe_key(article)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized.append(article)
        return normalized

    def dedupe_key(self, article: FetchedArticle) -> str:
        digest = hashlib.sha256()
        digest.update(article.canonical_url.encode("utf-8"))
        digest.update(article.title_normalized.encode("utf-8"))
        return digest.hexdigest()

    async def healthcheck(self) -> dict[str, str]:
        return {
            "status": "healthy" if self.source.active else "disabled",
            "connector": self.connector_name,
            "source_type": str(self.source.source_type),
        }

    def rate_limit_policy(self) -> dict[str, str]:
        return {
            "requests_per_hour": str(self.source.rate_limit_rph or 0),
            "polling_interval_minutes": str(self.source.polling_interval_minutes),
            "connector": self.connector_name,
        }

    def source_metadata(self) -> dict[str, str]:
        return {
            "name": self.source.name,
            "type": str(self.source.source_type),
            "vertical": self.source.content_vertical,
            "tier": self.source.source_tier,
            "category": self.source.category,
            "regions": ",".join(self.source.region_tags or []),
            "languages": ",".join(self.source.language_tags or []),
        }
