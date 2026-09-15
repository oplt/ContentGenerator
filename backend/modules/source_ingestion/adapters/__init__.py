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
from backend.modules.source_ingestion.adapters.base import (
    BaseSourceAdapter,
    FetchedArticle,
    canonicalize_url,
    normalize_title,
    tokenize_for_similarity,
)
from backend.modules.source_ingestion.adapters.factory import get_source_adapter
from backend.modules.source_ingestion.adapters.rss import RSSSourceAdapter, _parse_rss_date
from backend.modules.source_ingestion.adapters.sitemap import SitemapSourceAdapter

__all__ = [
    "APIBasedNewsAdapter",
    "BaseSourceAdapter",
    "BestEffortTrendsAdapter",
    "FetchedArticle",
    "GenericArticleParserAdapter",
    "GenericWebScrapeAdapter",
    "OfficialSourceAdapter",
    "RSSSourceAdapter",
    "RedditSourceAdapter",
    "SitemapSourceAdapter",
    "SocialSignalAdapter",
    "_parse_rss_date",
    "canonicalize_url",
    "get_source_adapter",
    "normalize_title",
    "tokenize_for_similarity",
]
