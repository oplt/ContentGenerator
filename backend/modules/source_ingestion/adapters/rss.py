from __future__ import annotations

import asyncio
import email.utils
from datetime import datetime, timezone
from typing import Any

import feedparser  # type: ignore[import-untyped]
import trafilatura

from backend.core.config import settings
from backend.core.http import map_concurrent
from backend.modules.source_ingestion.adapters.base import (
    BaseSourceAdapter,
    FetchedArticle,
    canonicalize_url,
)


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


class RSSSourceAdapter(BaseSourceAdapter):
    connector_name = "rss"

    async def _fetch_full_text(self, url: str) -> tuple[str | None, dict[str, str]]:
        try:
            html = await self._fetch_text(url)

            def _extract() -> str | None:
                return trafilatura.extract(
                    html,
                    include_comments=False,
                    no_fallback=False,
                    favor_precision=True,
                )

            extracted = await asyncio.to_thread(_extract)
            return extracted, {"parser": "trafilatura", "html_length": str(len(html))}
        except Exception as exc:
            return None, {"parser": "trafilatura", "error": str(exc)[:200]}

    def _article_from_entry(
        self,
        entry: Any,
        *,
        body: str | None,
        diagnostics: dict[str, str],
    ) -> FetchedArticle:
        url = entry.get("link") or self.source.url
        entry_id = entry.get("id")
        external_id = str(entry_id).strip() if entry_id not in (None, "") else None
        # canonical_url must always be a URL (article link). Feed GUIDs/hashes belong in
        # external_id; aggregator discussion links (e.g. HN item) go to source_item_url.
        metadata: dict[str, str] = {"source": self.source.name}
        if external_id and (
            external_id.startswith("http://") or external_id.startswith("https://")
        ):
            if canonicalize_url(external_id) != canonicalize_url(url):
                metadata["source_item_url"] = external_id
        return FetchedArticle(
            url=url,
            canonical_url=canonicalize_url(url),
            title=entry.get("title", "Untitled"),
            summary=entry.get("summary"),
            body=body,
            author=entry.get("author"),
            published_at=_parse_rss_date(entry),
            metadata=metadata,
            language=entry.get("language"),
            category_tags=list(self.source.category_tags or [self.source.category]),
            region_tags=list(self.source.region_tags or []),
            raw_payload={"entry": dict(entry)},
            external_id=external_id,
            parser_diagnostics=diagnostics,
        )

    async def fetch(self) -> list[FetchedArticle]:
        feed_text = await self._fetch_text(self.source.url)
        parsed = await asyncio.to_thread(feedparser.parse, feed_text)
        fetch_full_text = self.source.config.get("fetch_full_text", "false").lower() == "true"
        limit = int(self.source.config.get("limit", "15"))
        entries = list(parsed.entries[:limit])

        async def _build(entry: Any) -> FetchedArticle:
            url = entry.get("link") or self.source.url
            summary = entry.get("summary")
            body = summary
            diagnostics: dict[str, str] = {"entry_id": str(entry.get("id") or "")}
            if fetch_full_text and url != self.source.url:
                full_body, parser_diag = await self._fetch_full_text(url)
                diagnostics |= parser_diag
                if full_body and len(full_body) > len(summary or ""):
                    body = full_body
            return self._article_from_entry(entry, body=body, diagnostics=diagnostics)

        if not fetch_full_text:
            return [
                self._article_from_entry(
                    entry,
                    body=entry.get("summary"),
                    diagnostics={"entry_id": str(entry.get("id") or "")},
                )
                for entry in entries
            ]

        outcomes = await map_concurrent(
            entries,
            _build,
            limit=max(1, settings.HTTP_INGESTION_ENRICH_CONCURRENCY),
            return_exceptions=True,
        )
        articles: list[FetchedArticle] = []
        for index, outcome in enumerate(outcomes):
            if isinstance(outcome, Exception):
                entry = entries[index]
                articles.append(
                    self._article_from_entry(
                        entry,
                        body=entry.get("summary"),
                        diagnostics={
                            "entry_id": str(entry.get("id") or ""),
                            "enrich_error": str(outcome)[:200],
                        },
                    )
                )
            else:
                articles.append(outcome)
        return articles
