from __future__ import annotations

from datetime import timedelta
import json

import pytest
from fastapi import HTTPException

from backend.core.time_utils import utc_now_naive
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


@pytest.mark.asyncio
async def test_ingestion_failure_returns_http_error_and_persists_fetch_run(db_session, seeded_context, monkeypatch):
    service = SourceIngestionService(db_session)
    tenant = seeded_context["tenant"]

    source = await service.create_source(
        tenant.id,
        SourceCreateRequest(
            name="Broken RSS",
            source_type="rss",
            url="https://example.com/broken.xml",
        ),
    )
    await db_session.commit()

    class FailingAdapter:
        async def fetch(self):
            raise RuntimeError("upstream unavailable")

    class FakeRedis:
        async def get(self, key: str):
            return None

        async def setex(self, key: str, ttl: int, value: str):
            return None

    monkeypatch.setattr("backend.modules.source_ingestion.service.get_source_adapter", lambda source: FailingAdapter())
    monkeypatch.setattr("backend.modules.source_ingestion.service.redis_client", FakeRedis())

    with pytest.raises(HTTPException) as exc_info:
        await service.run_ingestion(tenant.id, source.id)

    await db_session.refresh(source)
    fetch_runs = await service.list_fetch_runs(tenant.id)

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Source fetch failed: upstream unavailable"
    assert fetch_runs[0].status == FetchRunStatus.FAILED.value
    assert fetch_runs[0].error_message == "upstream unavailable"
    assert source.failure_count == 1
    assert source.circuit_state == CircuitState.HALF_OPEN.value
    assert source.negative_cache_until is not None


@pytest.mark.asyncio
async def test_open_circuit_allows_naive_negative_cache_timestamp(db_session, seeded_context):
    service = SourceIngestionService(db_session)
    tenant = seeded_context["tenant"]

    source = await service.create_source(
        tenant.id,
        SourceCreateRequest(
            name="Circuit Source",
            source_type="rss",
            url="https://example.com/circuit.xml",
        ),
    )
    source.circuit_state = CircuitState.OPEN.value
    source.negative_cache_until = utc_now_naive() + timedelta(minutes=5)
    await db_session.commit()

    response = await service.run_ingestion(tenant.id, source.id)

    assert response.status == "circuit_open"
    assert response.raw_articles_ingested == 0
    assert response.clusters_updated == 0


@pytest.mark.asyncio
async def test_delete_source_soft_deletes_and_hides_from_listing(db_session, seeded_context, monkeypatch):
    service = SourceIngestionService(db_session)
    tenant = seeded_context["tenant"]

    source = await service.create_source(
        tenant.id,
        SourceCreateRequest(
            name="Delete Me",
            source_type="rss",
            url="https://example.com/delete-me.xml",
        ),
    )
    await db_session.commit()

    deleted_keys: list[str] = []

    class FakeRedis:
        async def delete(self, key: str):
            deleted_keys.append(key)
            return 1

    async def fake_record(self, **kwargs):
        return None

    monkeypatch.setattr("backend.modules.source_ingestion.service.redis_client", FakeRedis())
    monkeypatch.setattr("backend.modules.source_ingestion.service.AuditService.record", fake_record)

    await service.delete_source(tenant.id, source.id)
    await db_session.commit()

    sources = await service.list_sources(tenant.id)
    assert all(item.id != source.id for item in sources)
    assert deleted_keys == [f"ingestion:source:{source.id}:last_success"]
