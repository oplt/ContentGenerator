from __future__ import annotations

from copy import copy
from xml.etree import ElementTree

from backend.core.config import settings
from backend.core.http import map_concurrent
from backend.modules.source_ingestion.adapters.article import GenericArticleParserAdapter
from backend.modules.source_ingestion.adapters.base import BaseSourceAdapter, FetchedArticle
from backend.modules.source_ingestion.sitemap_walk import walk_sitemap_urls


class SitemapSourceAdapter(BaseSourceAdapter):
    connector_name = "sitemap"

    async def _walk_sitemap(self, url: str) -> list[str]:
        return await walk_sitemap_urls(
            url,
            fetch_text=self._fetch_text,
            parse_xml=ElementTree.fromstring,
            max_depth=int(self.source.config.get("max_sitemap_depth", "2")),
            max_urls=int(
                self.source.config.get("max_sitemap_urls", str(settings.HTTP_SITEMAP_DEFAULT_MAX_URLS))
            ),
            change_window_hours=int(self.source.config.get("change_window_hours", "72")),
            timeout_seconds=float(
                self.source.config.get(
                    "sitemap_timeout_seconds",
                    str(settings.HTTP_SITEMAP_DEFAULT_TIMEOUT_SECONDS),
                )
            ),
        )

    async def fetch(self) -> list[FetchedArticle]:
        limit = int(self.source.config.get("limit", "10"))
        urls = (await self._walk_sitemap(self.source.url))[:limit]

        async def _fetch_one(url: str) -> list[FetchedArticle]:
            if not await self._robots_allowed(url):
                return []
            parser_source = copy(self.source)
            parser_source.url = url
            return await GenericArticleParserAdapter(parser_source).fetch()

        outcomes = await map_concurrent(
            urls,
            _fetch_one,
            limit=max(1, settings.HTTP_INGESTION_ENRICH_CONCURRENCY),
            return_exceptions=True,
        )
        articles: list[FetchedArticle] = []
        for outcome in outcomes:
            if isinstance(outcome, Exception):
                continue
            articles.extend(outcome)
        return articles
