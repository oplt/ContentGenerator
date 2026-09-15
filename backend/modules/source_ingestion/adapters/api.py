from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import feedparser  # type: ignore[import-untyped]

from backend.core.config import settings
from backend.core.http import request
from backend.modules.source_ingestion.adapters.base import (
    BaseSourceAdapter,
    FetchedArticle,
    canonicalize_url,
)
from backend.modules.source_ingestion.adapters.rss import RSSSourceAdapter, _parse_rss_date


class APIBasedNewsAdapter(BaseSourceAdapter):
    connector_name = "api_news"

    async def fetch(self) -> list[FetchedArticle]:
        payload = await self._fetch_json(self.source.url)
        items_key = self.source.config.get("items_key", "items")
        title_key = self.source.config.get("title_key", "title")
        url_key = self.source.config.get("url_key", "url")
        summary_key = self.source.config.get("summary_key", "summary")
        body_key = self.source.config.get("body_key", "body")
        author_key = self.source.config.get("author_key", "author")
        items: list[dict[str, Any]] = payload.get(items_key, payload if isinstance(payload, list) else [])
        articles: list[FetchedArticle] = []
        for item in items[: int(self.source.config.get("limit", "15"))]:
            article_url = item.get(url_key) or self.source.url
            articles.append(
                FetchedArticle(
                    url=article_url,
                    canonical_url=canonicalize_url(article_url),
                    title=str(item.get(title_key, "Untitled")),
                    summary=item.get(summary_key),
                    body=item.get(body_key) or item.get(summary_key),
                    author=item.get(author_key),
                    published_at=None,
                    metadata={"source": self.source.name},
                    language=item.get("language"),
                    category_tags=list(self.source.category_tags or [self.source.category]),
                    region_tags=list(self.source.region_tags or []),
                    raw_payload=item,
                )
            )
        return articles


class RedditSourceAdapter(BaseSourceAdapter):
    connector_name = "reddit"

    async def _oauth_headers(self) -> dict[str, str]:
        client_id = self.source.config.get("client_id") or settings.REDDIT_CLIENT_ID
        client_secret = self.source.config.get("client_secret") or settings.REDDIT_CLIENT_SECRET
        user_agent = self.source.config.get("user_agent") or settings.REDDIT_USER_AGENT
        if not client_id or not client_secret:
            return {"User-Agent": user_agent}
        from backend.modules.source_ingestion.oauth_cache import get_reddit_client_credentials_token

        token = await get_reddit_client_credentials_token(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        if not token:
            return {"User-Agent": user_agent}
        return {
            "Authorization": f"Bearer {token}",
            "User-Agent": user_agent,
        }

    async def fetch(self) -> list[FetchedArticle]:
        subreddit = self.source.config.get("subreddit", "all")
        listing = self.source.config.get("listing", "hot")
        limit = int(self.source.config.get("limit", "15"))
        headers = await self._oauth_headers()
        if "Authorization" in headers:
            url = f"{settings.REDDIT_API_BASE_URL}/r/{subreddit}/{listing}?limit={limit}"
        else:
            url = self.source.url or f"https://www.reddit.com/r/{subreddit}/{listing}.json?limit={limit}"
        response = await request("GET", url, provider="ingestion", headers=headers)
        response.raise_for_status()
        payload = response.json()
        articles: list[FetchedArticle] = []
        for child in payload.get("data", {}).get("children", [])[:limit]:
            data = child.get("data", {})
            permalink = data.get("permalink") or ""
            post_url = data.get("url_overridden_by_dest") or data.get("url") or urljoin("https://www.reddit.com", permalink)
            created_utc = data.get("created_utc")
            published_at = datetime.fromtimestamp(float(created_utc), tz=timezone.utc) if created_utc is not None else None
            body = data.get("selftext") or data.get("title") or ""
            articles.append(
                FetchedArticle(
                    url=post_url,
                    canonical_url=canonicalize_url(post_url),
                    title=data.get("title", "Untitled Reddit post"),
                    summary=data.get("selftext")[:280] if data.get("selftext") else None,
                    body=body,
                    author=data.get("author"),
                    published_at=published_at,
                    metadata={
                        "source": self.source.name,
                        "subreddit": data.get("subreddit", subreddit),
                        "score": str(data.get("score", 0)),
                        "comments": str(data.get("num_comments", 0)),
                    },
                    language="en",
                    category_tags=list(self.source.category_tags or [self.source.category, data.get("subreddit", subreddit)]),
                    region_tags=list(self.source.region_tags or []),
                    raw_payload=data,
                    external_id=data.get("name"),
                )
            )
        return articles

    async def healthcheck(self) -> dict[str, str]:
        headers = await self._oauth_headers()
        return {
            "status": "healthy",
            "connector": self.connector_name,
            "auth_mode": "oauth" if "Authorization" in headers else "anonymous_json",
        }


class BestEffortTrendsAdapter(BaseSourceAdapter):
    connector_name = "google_trends"

    async def fetch(self) -> list[FetchedArticle]:
        if not settings.ENABLE_GOOGLE_TRENDS_CONNECTOR:
            return []
        region = self.source.config.get("geo", settings.GOOGLE_TRENDS_REGION)
        feed_url = self.source.url or f"{settings.GOOGLE_TRENDS_RSS_URL}?geo={region}"
        try:
            feed_text = await self._fetch_text(feed_url)
            parsed = await asyncio.to_thread(feedparser.parse, feed_text)
            return [
                FetchedArticle(
                    url=entry.get("link") or feed_url,
                    canonical_url=canonicalize_url(entry.get("link") or feed_url),
                    title=entry.get("title", "Trend"),
                    summary=entry.get("summary"),
                    body=entry.get("summary"),
                    author=None,
                    published_at=_parse_rss_date(entry) or datetime.now(timezone.utc),
                    metadata={"source": self.source.name, "best_effort": "true", "geo": region},
                    category_tags=list(self.source.category_tags or [self.source.category]),
                    region_tags=list(self.source.region_tags or [region]),
                    raw_payload={"entry": dict(entry)},
                )
                for entry in parsed.entries[: int(self.source.config.get("limit", "10"))]
            ]
        except Exception:
            return []

    async def healthcheck(self) -> dict[str, str]:
        return {
            "status": "healthy" if settings.ENABLE_GOOGLE_TRENDS_CONNECTOR else "disabled",
            "connector": self.connector_name,
            "best_effort": "true",
        }


class SocialSignalAdapter(BaseSourceAdapter):
    connector_name = "social_signal"

    async def fetch(self) -> list[FetchedArticle]:
        network = (self.source.config.get("network") or "").lower()
        seed_topics = [item.strip() for item in self.source.config.get("seed_topics", "").split(",") if item.strip()]
        if network == "x" and not settings.ENABLE_X_SIGNAL_CONNECTOR:
            return []
        if network == "bluesky" and not settings.ENABLE_BLUESKY_SIGNAL_CONNECTOR:
            return []
        mode = self.source.config.get("mode", "dry_run")
        if mode == "dry_run":
            return [
                FetchedArticle(
                    url=self.source.url,
                    canonical_url=canonicalize_url(self.source.url),
                    title=f"{network.upper()} signal: {topic}",
                    summary="Dry-run social signal placeholder",
                    body=f"Signal-only topic candidate from {network}: {topic}",
                    author=None,
                    published_at=datetime.now(timezone.utc),
                    metadata={"source": self.source.name, "network": network, "mode": "dry_run"},
                    category_tags=list(self.source.category_tags or [self.source.category]),
                    region_tags=list(self.source.region_tags or []),
                    raw_payload={"topic": topic, "dry_run": True},
                )
                for topic in seed_topics[: int(self.source.config.get("limit", "5"))]
            ]
        return []

    async def healthcheck(self) -> dict[str, str]:
        network = (self.source.config.get("network") or "").lower()
        enabled = (network == "x" and settings.ENABLE_X_SIGNAL_CONNECTOR) or (
            network == "bluesky" and settings.ENABLE_BLUESKY_SIGNAL_CONNECTOR
        )
        return {
            "status": "healthy" if enabled else "disabled",
            "connector": self.connector_name,
            "network": network,
            "mode": self.source.config.get("mode", "dry_run"),
        }


class OfficialSourceAdapter(RSSSourceAdapter):
    connector_name = "official_source"

    async def normalize(self, articles: list[FetchedArticle]) -> list[FetchedArticle]:
        normalized = await super().normalize(articles)
        template = self.source.config.get("official_template", "press")
        for article in normalized:
            article.metadata["official_template"] = template
            if template == "central_bank":
                article.category_tags = list(set(article.category_tags + ["economy", "official"]))
            elif template == "investor_relations":
                article.category_tags = list(set(article.category_tags + ["companies", "official"]))
            else:
                article.category_tags = list(set(article.category_tags + ["official"]))
        return normalized
