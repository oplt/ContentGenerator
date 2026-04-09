from __future__ import annotations

import hashlib
import json
import re
import urllib.robotparser
from copy import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from xml.etree import ElementTree

import email.utils

import feedparser
import httpx
import trafilatura
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from backend.core.config import settings
from backend.modules.source_ingestion.models import Source, SourceType


def normalize_title(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


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

    @retry(wait=wait_exponential_jitter(initial=1, max=8), stop=stop_after_attempt(settings.HTTP_MAX_RETRIES))
    async def _fetch_text(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        auth: tuple[str, str] | None = None,
        data: dict[str, str] | None = None,
        method: str = "GET",
    ) -> str:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.request(
                method,
                url,
                headers=headers or {"User-Agent": settings.APP_NAME},
                auth=auth,
                data=data,
            )
            response.raise_for_status()
            return response.text

    async def _fetch_json(self, url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        raw = await self._fetch_text(url, headers=headers)
        return json.loads(raw)

    async def _robots_allowed(self, url: str) -> bool:
        if not self.source.robots_respected:
            return True
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = urllib.robotparser.RobotFileParser()
        try:
            robots_text = await self._fetch_text(robots_url)
            parser.parse(robots_text.splitlines())
            return parser.can_fetch(settings.APP_NAME, url)
        except Exception:
            return True

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


def _parse_rss_date(entry: Any) -> datetime | None:
    if entry.get("published_parsed"):
        try:
            import calendar

            ts = calendar.timegm(entry["published_parsed"])
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            pass
    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            parsed = email.utils.parsedate_to_datetime(raw)
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


class GenericArticleParserAdapter(BaseSourceAdapter):
    connector_name = "article_parser"

    async def fetch(self) -> list[FetchedArticle]:
        url = self.source.url
        if not await self._robots_allowed(url):
            return []
        html = await self._fetch_text(url)
        downloaded = trafilatura.extract_metadata(html)
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            no_fallback=False,
            favor_precision=True,
            with_metadata=False,
        )
        title = (downloaded.title if downloaded and downloaded.title else self.source.name).strip()
        return [
            FetchedArticle(
                url=url,
                canonical_url=url,
                title=title,
                summary=(extracted[:280] if extracted else None),
                body=extracted,
                author=downloaded.author if downloaded else None,
                published_at=None,
                metadata={"source": self.source.name},
                language=(downloaded.language if downloaded else None),
                category_tags=list(self.source.category_tags or [self.source.category]),
                region_tags=list(self.source.region_tags or []),
                raw_payload={"html_length": str(len(html))},
                parser_diagnostics={
                    "parser": "trafilatura",
                    "html_length": str(len(html)),
                    "extracted_chars": str(len(extracted or "")),
                },
            )
        ]


class RSSSourceAdapter(BaseSourceAdapter):
    connector_name = "rss"

    async def _fetch_full_text(self, url: str) -> tuple[str | None, dict[str, str]]:
        try:
            html = await self._fetch_text(url)
            extracted = trafilatura.extract(
                html,
                include_comments=False,
                no_fallback=False,
                favor_precision=True,
            )
            return extracted, {"parser": "trafilatura", "html_length": str(len(html))}
        except Exception as exc:
            return None, {"parser": "trafilatura", "error": str(exc)[:200]}

    async def fetch(self) -> list[FetchedArticle]:
        feed_text = await self._fetch_text(self.source.url)
        parsed = feedparser.parse(feed_text)
        fetch_full_text = self.source.config.get("fetch_full_text", "false").lower() == "true"
        limit = int(self.source.config.get("limit", "15"))
        articles: list[FetchedArticle] = []
        for entry in parsed.entries[:limit]:
            url = entry.get("link") or self.source.url
            canonical_url = canonicalize_url(entry.get("id") or url)
            summary = entry.get("summary")
            body = summary
            diagnostics: dict[str, str] = {"entry_id": str(entry.get("id") or "")}
            if fetch_full_text and url != self.source.url:
                full_body, parser_diag = await self._fetch_full_text(url)
                diagnostics |= parser_diag
                if full_body and len(full_body) > len(summary or ""):
                    body = full_body
            articles.append(
                FetchedArticle(
                    url=url,
                    canonical_url=canonical_url,
                    title=entry.get("title", "Untitled"),
                    summary=summary,
                    body=body,
                    author=entry.get("author"),
                    published_at=_parse_rss_date(entry),
                    metadata={"source": self.source.name},
                    language=entry.get("language"),
                    category_tags=list(self.source.category_tags or [self.source.category]),
                    region_tags=list(self.source.region_tags or []),
                    raw_payload={"entry": dict(entry)},
                    parser_diagnostics=diagnostics,
                )
            )
        return articles


class GenericWebScrapeAdapter(BaseSourceAdapter):
    connector_name = "generic_web"

    async def fetch(self) -> list[FetchedArticle]:
        return await GenericArticleParserAdapter(self.source).fetch()


class SitemapSourceAdapter(BaseSourceAdapter):
    connector_name = "sitemap"

    def _extract_urls(self, root: ElementTree.Element) -> tuple[list[str], list[tuple[str, datetime | None]]]:
        namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        sitemap_nodes = [item.text for item in root.findall(".//ns:sitemap/ns:loc", namespace) if item.text]
        url_nodes: list[tuple[str, datetime | None]] = []
        for url_node in root.findall(".//ns:url", namespace):
            loc = url_node.findtext("ns:loc", namespaces=namespace)
            lastmod_raw = url_node.findtext("ns:lastmod", namespaces=namespace)
            lastmod = None
            if lastmod_raw:
                try:
                    parsed = datetime.fromisoformat(lastmod_raw.replace("Z", "+00:00"))
                    lastmod = parsed.astimezone(timezone.utc)
                except Exception:
                    lastmod = None
            if loc:
                url_nodes.append((loc, lastmod))
        return sitemap_nodes, url_nodes

    async def _walk_sitemap(self, url: str, depth: int = 0) -> list[str]:
        if depth > int(self.source.config.get("max_sitemap_depth", "2")):
            return []
        xml_text = await self._fetch_text(url)
        root = ElementTree.fromstring(xml_text)
        sitemap_nodes, url_nodes = self._extract_urls(root)
        collected: list[str] = []
        change_window_hours = int(self.source.config.get("change_window_hours", "72"))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=change_window_hours)
        for loc, lastmod in url_nodes:
            if lastmod and lastmod < cutoff:
                continue
            collected.append(loc)
        for nested in sitemap_nodes:
            collected.extend(await self._walk_sitemap(nested, depth + 1))
        return collected

    async def fetch(self) -> list[FetchedArticle]:
        limit = int(self.source.config.get("limit", "10"))
        urls = await self._walk_sitemap(self.source.url)
        parser_adapter = GenericArticleParserAdapter(self.source)
        articles: list[FetchedArticle] = []
        for url in urls[:limit]:
            if not await self._robots_allowed(url):
                continue
            parser_source = copy(self.source)
            parser_source.url = url
            parsed_articles = await GenericArticleParserAdapter(parser_source).fetch()
            articles.extend(parsed_articles)
        return articles


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
        if not client_id or not client_secret:
            return {"User-Agent": self.source.config.get("user_agent") or settings.REDDIT_USER_AGENT}
        token_text = await self._fetch_text(
            settings.REDDIT_TOKEN_URL,
            method="POST",
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": self.source.config.get("user_agent") or settings.REDDIT_USER_AGENT},
        )
        payload = json.loads(token_text)
        return {
            "Authorization": f"Bearer {payload['access_token']}",
            "User-Agent": self.source.config.get("user_agent") or settings.REDDIT_USER_AGENT,
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
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS, follow_redirects=True, headers=headers) as client:
            response = await client.get(url)
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
            parsed = feedparser.parse(feed_text)
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


def get_source_adapter(source: Source) -> BaseSourceAdapter:
    if source.parser_type == "article_parser":
        return GenericArticleParserAdapter(source)
    if source.source_type == SourceType.RSS.value:
        return RSSSourceAdapter(source)
    if source.source_type == SourceType.SITEMAP.value or source.source_type == SourceType.BLOG.value:
        return SitemapSourceAdapter(source)
    if source.source_type == SourceType.API.value:
        return APIBasedNewsAdapter(source)
    if source.source_type == SourceType.REDDIT.value:
        return RedditSourceAdapter(source)
    if source.source_type == SourceType.TREND.value:
        return BestEffortTrendsAdapter(source)
    if source.source_type == SourceType.SOCIAL.value:
        return SocialSignalAdapter(source)
    if source.source_type == SourceType.OFFICIAL.value:
        return OfficialSourceAdapter(source)
    return GenericWebScrapeAdapter(source)
