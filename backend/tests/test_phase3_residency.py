"""Phase 3 residency: split ingestion phases + batched asset persistence."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.content_generation.service import ContentGenerationService
from backend.modules.source_ingestion.ingestion_workflow import (
    PreparedIngestion,
    _unbound_source_copy,
    run_ingestion_workflow,
)


def test_unbound_source_copy_is_detached_snapshot() -> None:
    source_id = uuid4()
    tenant_id = uuid4()
    source = SimpleNamespace(
        id=source_id,
        tenant_id=tenant_id,
        name="Feed",
        source_type="rss",
        url="https://example.test/feed",
        parser_type="auto",
        category="general",
        category_tags=["news"],
        region_tags=["us"],
        language_tags=["en"],
        source_tier="signal",
        content_vertical="general",
        freshness_decay_hours=24,
        legal_risk=False,
        rate_limit_rph=None,
        tier1_confirmation_required=False,
        config={"limit": "5"},
        polling_config={},
        parser_config={},
        polling_interval_minutes=30,
        trust_score=0.8,
        active=True,
        robots_respected=True,
        failure_count=0,
        success_count=1,
        circuit_state="closed",
        negative_cache_until=None,
        last_polled_at=None,
        next_poll_at=None,
        last_success_at=None,
        disabled_reason=None,
        last_error=None,
        stale_cache_ttl_seconds=3600,
        version=1,
        created_at=None,
        updated_at=None,
        deleted_at=None,
    )
    copy = _unbound_source_copy(cast(Any, source))
    assert copy.id == source_id
    assert copy.config == {"limit": "5"}
    assert copy.config is not source.config


def test_run_ingestion_workflow_fetches_outside_db_sessions() -> None:
    prepared = PreparedIngestion(
        tenant_id=uuid4(),
        source_id=uuid4(),
        fetch_run_id=uuid4(),
        source=cast(Any, SimpleNamespace(id=uuid4())),
    )
    calls: list[str] = []

    async def fake_prepare(**kwargs: object) -> PreparedIngestion:
        calls.append("prepare")
        return prepared

    async def fake_fetch(source: object) -> tuple[list[object], bool, dict[str, str]]:
        calls.append("fetch")
        return [], True, {"status": "healthy"}

    async def fake_persist(**kwargs: object) -> object:
        calls.append("persist")
        return SimpleNamespace(status="success")

    async def _run() -> None:
        with (
            patch(
                "backend.modules.source_ingestion.ingestion_workflow.prepare_ingestion",
                fake_prepare,
            ),
            patch(
                "backend.modules.source_ingestion.ingestion_workflow.fetch_articles_outside_db",
                fake_fetch,
            ),
            patch(
                "backend.modules.source_ingestion.ingestion_workflow.persist_fetch_success",
                fake_persist,
            ),
        ):
            result = await run_ingestion_workflow(tenant_id=prepared.tenant_id, source_id=prepared.source_id)
        assert result.status == "success"
        assert calls == ["prepare", "fetch", "persist"]

    asyncio.run(_run())


def test_create_assets_batch_flushes_once() -> None:
    flush = AsyncMock()
    added: list[object] = []

    class FakeSession:
        def add_all(self, items: list[object]) -> None:
            added.extend(items)

        async def flush(self) -> None:
            await flush()

    service = ContentGenerationService(cast(AsyncSession, FakeSession()))

    async def _run() -> None:
        assets = await service._create_assets_batch(
            [
                {
                    "tenant_id": uuid4(),
                    "asset_group_id": uuid4(),
                    "content_job_id": uuid4(),
                    "asset_type": "text_variant",
                    "platform": "x",
                    "variant_label": "A",
                    "text_content": "hello",
                    "source_trace": {"stage": "writer"},
                },
                {
                    "tenant_id": uuid4(),
                    "asset_group_id": uuid4(),
                    "content_job_id": uuid4(),
                    "asset_type": "caption",
                    "platform": "x",
                    "variant_label": "B",
                    "text_content": "world",
                    "source_trace": {"stage": "writer"},
                },
            ]
        )
        assert len(assets) == 2
        assert len(added) == 2
        assert flush.await_count == 1

    asyncio.run(_run())
