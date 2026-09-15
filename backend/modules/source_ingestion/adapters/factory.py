from __future__ import annotations

from backend.modules.source_ingestion.adapters.api import (
    APIBasedNewsAdapter,
    BestEffortTrendsAdapter,
    OfficialSourceAdapter,
    RedditSourceAdapter,
    SocialSignalAdapter,
)
from backend.modules.source_ingestion.adapters.article import (
    GenericArticleParserAdapter,
    GenericWebScrapeAdapter,
)
from backend.modules.source_ingestion.adapters.base import BaseSourceAdapter
from backend.modules.source_ingestion.adapters.rss import RSSSourceAdapter
from backend.modules.source_ingestion.adapters.sitemap import SitemapSourceAdapter
from backend.modules.source_ingestion.models import Source, SourceType


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
