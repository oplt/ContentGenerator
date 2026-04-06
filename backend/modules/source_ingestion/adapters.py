from __future__ import annotations

import asyncio
import hashlib
import json
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import email.utils

import feedparser
import httpx
import trafilatura
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from backend.core.config import settings
from backend.modules.source_ingestion.models import Source, SourceType


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

    @property
    def content_hash(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.canonical_url.encode("utf-8"))
        digest.update((self.title or "").encode("utf-8"))
        digest.update((self.body or self.summary or "").encode("utf-8"))
        return digest.hexdigest()


class BaseSourceAdapter:
    def __init__(self, source: Source):
        self.source = source

    @retry(wait=wait_exponential_jitter(initial=1, max=8), stop=stop_after_attempt(settings.HTTP_MAX_RETRIES))
    async def _fetch_text(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": settings.APP_NAME})
            response.raise_for_status()
            return response.text

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


def _parse_rss_date(entry: Any) -> datetime | None:
    """Try published_parsed (struct_time) first, then parse the raw string."""
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
            return email.utils.parsedate_to_datetime(raw)
        except Exception:
            pass
    return None


class RSSSourceAdapter(BaseSourceAdapter):
    async def _fetch_full_text(self, url: str) -> str | None:
        """Fetch the full article body using trafilatura. Returns None on any failure."""
        try:
            html = await self._fetch_text(url)
            return trafilatura.extract(
                html,
                include_comments=False,
                no_fallback=False,
                favor_precision=True,
            )
        except Exception:
            return None

    async def fetch(self) -> list[FetchedArticle]:
        feed_text = await self._fetch_text(self.source.url)
        parsed = feedparser.parse(feed_text)
        fetch_full_text = self.source.config.get("fetch_full_text", "false").lower() == "true"
        articles: list[FetchedArticle] = []
        for entry in parsed.entries[: int(self.source.config.get("limit", "15"))]:
            url = entry.get("link") or self.source.url
            summary = entry.get("summary")
            body = summary  # fallback
            if fetch_full_text and url != self.source.url:
                full_body = await self._fetch_full_text(url)
                if full_body and len(full_body) > len(summary or ""):
                    body = full_body
            articles.append(
                FetchedArticle(
                    url=url,
                    canonical_url=url,
                    title=entry.get("title", "Untitled"),
                    summary=summary,
                    body=body,
                    author=entry.get("author"),
                    published_at=_parse_rss_date(entry),
                    metadata={"source": self.source.name},
                )
            )
        return articles


class GenericWebScrapeAdapter(BaseSourceAdapter):
    async def fetch(self) -> list[FetchedArticle]:
        if not await self._robots_allowed(self.source.url):
            return []
        html = await self._fetch_text(self.source.url)
        extracted = trafilatura.extract(html)
        soup = BeautifulSoup(html, "html.parser")
        title = (soup.title.string if soup.title and soup.title.string else self.source.name).strip()
        return [
            FetchedArticle(
                url=self.source.url,
                canonical_url=self.source.url,
                title=title,
                summary=(extracted[:280] if extracted else None),
                body=extracted,
                author=None,
                published_at=None,
                metadata={"source": self.source.name},
            )
        ]


class SitemapSourceAdapter(BaseSourceAdapter):
    async def fetch(self) -> list[FetchedArticle]:
        xml_text = await self._fetch_text(self.source.url)
        root = ElementTree.fromstring(xml_text)
        namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [item.text for item in root.findall(".//ns:loc", namespace) if item.text][: int(self.source.config.get("limit", "5"))]
        adapter = GenericWebScrapeAdapter(self.source)
        articles: list[FetchedArticle] = []
        for url in urls:
            if not url:
                continue
            if not await self._robots_allowed(url):
                continue
            html = await adapter._fetch_text(url)
            extracted = trafilatura.extract(html)
            soup = BeautifulSoup(html, "html.parser")
            title = (soup.title.string if soup.title and soup.title.string else url).strip()
            articles.append(
                FetchedArticle(
                    url=url,
                    canonical_url=url,
                    title=title,
                    summary=(extracted[:280] if extracted else None),
                    body=extracted,
                    author=None,
                    published_at=None,
                    metadata={"source": self.source.name},
                )
            )
        return articles


class APIBasedNewsAdapter(BaseSourceAdapter):
    async def fetch(self) -> list[FetchedArticle]:
        raw_text = await self._fetch_text(self.source.url)
        payload = json.loads(raw_text)
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
                    canonical_url=article_url,
                    title=str(item.get(title_key, "Untitled")),
                    summary=item.get(summary_key),
                    body=item.get(body_key) or item.get(summary_key),
                    author=item.get(author_key),
                    published_at=None,
                    metadata={"source": self.source.name},
                )
            )
        return articles


def get_source_adapter(source: Source) -> BaseSourceAdapter:
    if source.source_type == SourceType.RSS.value:
        return RSSSourceAdapter(source)
    if source.source_type == SourceType.SITEMAP.value:
        return SitemapSourceAdapter(source)
    if source.source_type == SourceType.API.value:
        return APIBasedNewsAdapter(source)
    return GenericWebScrapeAdapter(source)
