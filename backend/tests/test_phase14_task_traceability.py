"""Ops Phase 14: Celery task_id must appear on successful ingestion results."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch
from uuid import uuid4

from backend.modules.source_ingestion.ingestion_workflow import (
    PreparedIngestion,
    _stamp_task_id,
    run_ingestion_workflow,
)
from backend.modules.source_ingestion.schemas import IngestionTriggerResponse
from backend.modules.source_ingestion.service import SourceIngestionService


def test_stamp_task_id_fills_missing_celery_id() -> None:
    response = IngestionTriggerResponse(
        source_id=uuid4(),
        status="success",
        raw_articles_ingested=1,
        clusters_updated=1,
        fetch_run_id=uuid4(),
        task_id=None,
    )
    stamped = _stamp_task_id(response, celery_task_id="celery-abc-123")
    assert stamped.task_id == "celery-abc-123"


def test_stamp_task_id_preserves_existing() -> None:
    response = IngestionTriggerResponse(
        source_id=uuid4(),
        status="queued",
        raw_articles_ingested=0,
        clusters_updated=0,
        task_id="preassigned",
    )
    stamped = _stamp_task_id(response, celery_task_id="other")
    assert stamped.task_id == "preassigned"


def test_run_ingestion_workflow_success_includes_task_id() -> None:
    celery_id = f"task-{uuid4()}"
    prepared = PreparedIngestion(
        tenant_id=uuid4(),
        source_id=uuid4(),
        fetch_run_id=uuid4(),
        source=cast(Any, SimpleNamespace(id=uuid4())),
        celery_task_id=celery_id,
        correlation_id="corr-1",
    )

    async def fake_prepare(**kwargs: object) -> PreparedIngestion:
        assert kwargs.get("celery_task_id") == celery_id
        return prepared

    async def fake_fetch(source: object) -> tuple[list[object], bool, dict[str, str]]:
        return [], True, {"status": "ok"}

    async def fake_persist(**kwargs: object) -> IngestionTriggerResponse:
        return IngestionTriggerResponse(
            source_id=prepared.source_id,
            status="success",
            raw_articles_ingested=0,
            clusters_updated=0,
            fetch_run_id=prepared.fetch_run_id,
            task_id=None,
        )

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
            result = await run_ingestion_workflow(
                tenant_id=prepared.tenant_id,
                source_id=prepared.source_id,
                celery_task_id=celery_id,
                correlation_id="corr-1",
            )
        assert result.task_id == celery_id
        assert result.status == "success"

    asyncio.run(_run())


def test_queue_ingestion_preassigns_celery_task_id() -> None:
    tenant_id = uuid4()
    source_id = uuid4()

    class FakeRepo:
        async def get_open_fetch_run(self, **kwargs: object) -> None:
            return None

        async def create_fetch_run(self, run: Any) -> Any:
            run.id = uuid4()
            return run

    class FakeService(SourceIngestionService):
        def __init__(self) -> None:
            self.db = cast(Any, MagicMock())
            self.repo = cast(Any, FakeRepo())

        async def get_source(self, tenant_id: Any, source_id: Any) -> Any:
            return SimpleNamespace(id=source_id, tenant_id=tenant_id)

    async def _run() -> None:
        svc = FakeService()
        run, created = await SourceIngestionService.queue_ingestion(
            svc,
            tenant_id,
            source_id,
            correlation_id="http-corr",
        )
        assert created is True
        meta = run.fetch_metadata
        assert isinstance(meta.get("celery_task_id"), str)
        assert len(str(meta["celery_task_id"])) > 8
        assert meta.get("correlation_id") == "http-corr"
        assert meta.get("trigger") == "manual"

    asyncio.run(_run())


def test_ingest_source_task_result_always_has_task_id() -> None:
    from backend.workers.task_defs import ingestion as ingestion_mod

    celery_id = str(uuid4())
    tenant_id = uuid4()
    source_id = uuid4()

    async def fake_workflow(**kwargs: object) -> IngestionTriggerResponse:
        assert kwargs["celery_task_id"] == celery_id
        return IngestionTriggerResponse(
            source_id=source_id,
            status="success",
            raw_articles_ingested=1,
            clusters_updated=1,
            fetch_run_id=uuid4(),
            task_id=None,
        )

    def fake_detached(**kwargs: object) -> IngestionTriggerResponse:
        operation = cast(
            Callable[[], Awaitable[IngestionTriggerResponse]],
            kwargs["operation"],
        )
        return asyncio.run(operation())

    with (
        patch(
            "backend.workers.task_defs.ingestion.run_ingestion_workflow",
            fake_workflow,
        ),
        patch(
            "backend.workers.task_defs.ingestion.run_detached_async_task",
            fake_detached,
        ),
    ):
        ingestion_mod.ingest_source_task.push_request(id=celery_id)
        try:
            payload = ingestion_mod.ingest_source_task(
                tenant_id=str(tenant_id),
                source_id=str(source_id),
                correlation_id="corr-x",
            )
        finally:
            ingestion_mod.ingest_source_task.pop_request()
    assert payload["task_id"] == celery_id
    assert payload["status"] == "success"
