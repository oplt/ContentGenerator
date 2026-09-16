"""RSS adapter: canonical_url is always a URL; feed IDs stay in external_id."""

from __future__ import annotations

from uuid import uuid4

from backend.modules.source_ingestion.adapters.base import canonicalize_url
from backend.modules.source_ingestion.adapters.rss import RSSSourceAdapter
from backend.modules.source_ingestion.models import Source


def _adapter() -> RSSSourceAdapter:
    source = Source(
        id=uuid4(),
        tenant_id=uuid4(),
        name="Test RSS",
        url="https://feeds.example.test/rss",
        source_type="rss",
        category="technology",
        category_tags=["technology"],
        region_tags=[],
        config={},
    )
    return RSSSourceAdapter(source)


def test_wired_style_guid_hash_is_external_id_not_canonical() -> None:
    adapter = _adapter()
    article_url = "https://www.wired.com/review/apple-iphone-18-pro/"
    article = adapter._article_from_entry(
        {"link": article_url, "id": "6aa86e680158a74c9d2d874b", "title": "Review"},
        body="summary",
        diagnostics={},
    )
    assert article.url == article_url
    assert article.canonical_url == canonicalize_url(article_url)
    assert article.external_id == "6aa86e680158a74c9d2d874b"
    assert "source_item_url" not in article.metadata


def test_hn_style_discussion_id_becomes_source_item_url() -> None:
    adapter = _adapter()
    article_url = "https://stale.jock.pl/"
    hn_item = "https://news.ycombinator.com/item?id=49726343"
    article = adapter._article_from_entry(
        {"link": article_url, "id": hn_item, "title": "Show HN"},
        body="summary",
        diagnostics={},
    )
    assert article.canonical_url == canonicalize_url(article_url)
    assert article.external_id == hn_item
    assert article.metadata["source_item_url"] == hn_item


def test_list_recent_raw_articles_resolves_timedelta_from_mixin() -> None:
    """Regression: SourceRepository must not shadow mixin with missing timedelta."""
    import inspect

    from backend.modules.source_ingestion.article_repository import ArticleRepositoryMixin
    from backend.modules.source_ingestion.repository import SourceRepository

    assert "list_recent_raw_articles" not in SourceRepository.__dict__
    assert "list_recent_raw_articles" in ArticleRepositoryMixin.__dict__
    source = inspect.getsource(SourceRepository.list_recent_raw_articles)
    assert "timedelta" in source
    assert "within_hours" in source
