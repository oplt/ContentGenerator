from __future__ import annotations

from backend.modules.source_ingestion.models import RawArticle, Source, SourceType
from backend.modules.story_intelligence.service import StoryIntelligenceService


async def test_story_intelligence_clusters_articles(db_session, seeded_context):
    tenant = seeded_context["tenant"]
    source = Source(
        tenant_id=tenant.id,
        name="Tech Feed",
        source_type=SourceType.RSS.value,
        url="https://example.com/rss",
        parser_type="auto",
        category="technology",
        trust_score=0.9,
    )
    db_session.add(source)
    await db_session.flush()

    raw_article = RawArticle(
        tenant_id=tenant.id,
        source_id=source.id,
        url="https://example.com/article-1",
        canonical_url="https://example.com/article-1",
        content_hash="hash-1",
        title="AI startup ships new autonomous editor",
        summary="A startup released a new AI editor for social teams.",
        body="A startup released a new AI editor for social teams and content operations.",
        extraction_confidence=0.9,
        source_metadata={"source": "Tech Feed"},
    )
    db_session.add(raw_article)
    await db_session.commit()

    service = StoryIntelligenceService(db_session)
    clusters = await service.process_articles(source=source, raw_articles=[raw_article])

    assert len(clusters) == 1
    assert clusters[0].headline == raw_article.title
    assert clusters[0].article_count >= 1
