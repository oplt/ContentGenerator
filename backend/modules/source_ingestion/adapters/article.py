from __future__ import annotations

import asyncio
from typing import Any

import trafilatura

from backend.modules.source_ingestion.adapters.base import BaseSourceAdapter, FetchedArticle


class GenericArticleParserAdapter(BaseSourceAdapter):
    connector_name = "article_parser"

    async def fetch(self) -> list[FetchedArticle]:
        url = self.source.url
        if not await self._robots_allowed(url):
            return []
        html = await self._fetch_text(url)

        def _parse() -> tuple[Any, str | None]:
            downloaded = trafilatura.extract_metadata(html)
            extracted = trafilatura.extract(
                html,
                include_comments=False,
                no_fallback=False,
                favor_precision=True,
                with_metadata=False,
            )
            return downloaded, extracted

        downloaded, extracted = await asyncio.to_thread(_parse)
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


class GenericWebScrapeAdapter(BaseSourceAdapter):
    connector_name = "generic_web"

    async def fetch(self) -> list[FetchedArticle]:
        return await GenericArticleParserAdapter(self.source).fetch()
