"""Ops Phase 13: DB sessions must not span Ollama/network I/O."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.modules.source_ingestion.ingestion_workflow import (
    PreparedIngestion,
    persist_fetch_success,
)
from backend.modules.source_ingestion.schemas import IngestionTriggerResponse
from backend.modules.story_intelligence.cluster_enrichment import enrich_raw_articles_outside_db
from backend.modules.story_intelligence.cluster_pipeline import ClusterPipelineMixin


def test_process_articles_refuses_in_session_llm() -> None:
    class Stub(ClusterPipelineMixin):
        pass

    with pytest.raises(RuntimeError, match="enrich_raw_articles_outside_db"):
        asyncio.run(Stub().process_articles(source=cast(Any, object()), raw_articles=[]))


def test_persist_fetch_success_enriches_after_session_closes() -> None:
    tenant_id = uuid4()
    source_id = uuid4()
    fetch_run_id = uuid4()
    prepared = PreparedIngestion(
        tenant_id=tenant_id,
        source_id=source_id,
        fetch_run_id=fetch_run_id,
        source=cast(Any, SimpleNamespace(id=source_id)),
    )
    raw_ids = [uuid4(), uuid4()]
    order: list[str] = []
    response = IngestionTriggerResponse(
        source_id=source_id,
        status="success",
        raw_articles_ingested=2,
        clusters_updated=0,
        fetch_run_id=fetch_run_id,
    )

    class _Scope:
        async def __aenter__(self) -> MagicMock:
            order.append("session_enter")
            db = MagicMock()
            db.get = AsyncMock(return_value=SimpleNamespace(started_at=None, fetch_metadata={}))
            return db

        async def __aexit__(self, *args: object) -> None:
            order.append("session_exit")

    async def fake_persist_body(**kwargs: object) -> tuple[IngestionTriggerResponse, list]:
        order.append("persist_body")
        return response, raw_ids

    async def fake_enrich(**kwargs: object) -> list:
        order.append("enrich")
        assert "session_exit" in order
        return [uuid4()]

    async def _run() -> None:
        with (
            patch(
                "backend.modules.source_ingestion.ingestion_workflow.session_scope",
                return_value=_Scope(),
            ),
            patch(
                "backend.modules.source_ingestion.ingestion_workflow.SourceRepository",
            ) as repo_cls,
            patch(
                "backend.modules.source_ingestion.ingestion_workflow._persist_success_body",
                fake_persist_body,
            ),
            patch(
                "backend.modules.story_intelligence.cluster_enrichment.enrich_raw_articles_outside_db",
                fake_enrich,
            ),
        ):
            repo = repo_cls.return_value
            repo.get_source = AsyncMock(return_value=SimpleNamespace(id=source_id, tenant_id=tenant_id))
            repo.create_health_event = AsyncMock()
            result = await persist_fetch_success(
                prepared=prepared,
                fetched_articles=[],
                live_fetch_succeeded=True,
            )
        assert result.clusters_updated == 1
        assert order == ["session_enter", "persist_body", "session_exit", "enrich"]

    asyncio.run(_run())


def test_enrich_raw_articles_outside_db_releases_before_embed() -> None:
    tenant_id = uuid4()
    source_id = uuid4()
    raw_id = uuid4()
    open_scopes = 0
    max_open_during_embed = 0
    embed_calls = 0

    class _Scope:
        def __init__(self) -> None:
            self.active = False

        async def __aenter__(self) -> MagicMock:
            nonlocal open_scopes
            self.active = True
            open_scopes += 1
            return MagicMock()

        async def __aexit__(self, *args: object) -> None:
            nonlocal open_scopes
            self.active = False
            open_scopes -= 1

    snap = SimpleNamespace(
        raw_id=raw_id,
        tenant_id=tenant_id,
        title="Title",
        body="Body text about markets and policy",
        source_id=source_id,
        existing_normalized_id=None,
        trust_score=0.9,
        source_tier="signal",
        content_vertical="general",
        source_name="Feed",
        recent_clusters=(),
    )

    async def fake_load(**kwargs: object) -> Any:
        return snap

    async def fake_embed(text: str) -> list[float]:
        nonlocal embed_calls, max_open_during_embed
        embed_calls += 1
        max_open_during_embed = max(max_open_during_embed, open_scopes)
        return [0.1, 0.2, 0.3]

    async def fake_cached_embedding(**kwargs: object) -> list[float]:
        factory = cast(Callable[[], Awaitable[list[float]]], kwargs["factory"])
        return await factory()

    async def fake_cached_summary(**kwargs: object) -> str:
        nonlocal max_open_during_embed
        max_open_during_embed = max(max_open_during_embed, open_scopes)
        return "summary"

    async def fake_persist(**kwargs: object) -> Any:
        return uuid4()

    async def _run() -> None:
        with (
            patch(
                "backend.modules.story_intelligence.cluster_enrichment.session_scope",
                side_effect=lambda: _Scope(),
            ),
            patch(
                "backend.modules.story_intelligence.cluster_enrichment._load_snap",
                fake_load,
            ),
            patch(
                "backend.modules.story_intelligence.cluster_enrichment.get_embeddings_provider",
            ) as emb,
            patch(
                "backend.modules.story_intelligence.cluster_enrichment.cached_embedding",
                fake_cached_embedding,
            ),
            patch(
                "backend.modules.story_intelligence.cluster_enrichment.cached_summary",
                fake_cached_summary,
            ),
            patch(
                "backend.modules.story_intelligence.cluster_enrichment._persist_enriched",
                fake_persist,
            ),
            patch(
                "backend.modules.story_intelligence.cluster_enrichment.StoryIntelligenceService",
            ) as svc_cls,
        ):
            emb.return_value.embed = fake_embed
            svc_cls.return_value.repo.find_near_duplicate = AsyncMock(return_value=None)
            ids = await enrich_raw_articles_outside_db(
                tenant_id=tenant_id,
                source_id=source_id,
                raw_article_ids=[raw_id],
            )
        assert len(ids) == 1
        assert embed_calls == 1
        assert max_open_during_embed == 0

    asyncio.run(_run())
