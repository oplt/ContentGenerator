from __future__ import annotations

import json

import pytest

from backend.modules.source_ingestion.models import CircuitState, FetchRunStatus
from backend.modules.source_ingestion.schemas import SourceCreateRequest
from backend.modules.source_ingestion.service import SourceIngestionService


@pytest.mark.asyncio
async def test_cached_fallback_keeps_partial_status_and_open_circuit(db_session, seeded_context, monkeypatch):
    service = SourceIngestionService(db_session)
    tenant = seeded_context["tenant"]

    source = await service.create_source(
        tenant.id,
        SourceCreateRequest(
            name="Example RSS",
            source_type="rss",
            url="https://example.com/feed.xml",
        ),
    )
    await db_session.commit()

    class FailingAdapter:
        async def fetch(self):
            raise RuntimeError("upstream unavailable")

    class FakeRedis:
        async def get(self, key: str):
            return json.dumps(
                [
                    {
                        "url": "https://example.com/story",
                        "canonical_url": "https://example.com/story",
                        "title": "Cached story",
                        "summary": "Cached summary",
                        "body": "Cached body",
                        "author": "Cache Bot",
                        "metadata": {"source": "cache"},
                    }
                ]
            )

        async def setex(self, key: str, ttl: int, value: str):
            return None

    async def fake_process_articles(self, source, raw_articles):
        return []

    async def fake_record(self, **kwargs):
        return None

    monkeypatch.setattr("backend.modules.source_ingestion.service.get_source_adapter", lambda source: FailingAdapter())
    monkeypatch.setattr("backend.modules.source_ingestion.service.redis_client", FakeRedis())
    monkeypatch.setattr(
        "backend.modules.source_ingestion.service.StoryIntelligenceService.process_articles",
        fake_process_articles,
    )
    monkeypatch.setattr("backend.modules.source_ingestion.service.AuditService.record", fake_record)

    response = await service.run_ingestion(tenant.id, source.id)
    await db_session.refresh(source)
    fetch_runs = await service.list_fetch_runs(tenant.id)

    assert response.status == FetchRunStatus.PARTIAL.value
    assert response.raw_articles_ingested == 1
    assert fetch_runs[0].status == FetchRunStatus.PARTIAL.value
    assert fetch_runs[0].response_cache_hit is True
    assert source.success_count == 0
    assert source.failure_count == 1
    assert source.circuit_state == CircuitState.HALF_OPEN.value
    assert source.negative_cache_until is not None

