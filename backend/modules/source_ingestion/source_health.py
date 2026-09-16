"""Concurrent source connector health collection."""

from __future__ import annotations

from uuid import UUID

from backend.core.config import settings
from backend.core.http import map_concurrent
from backend.modules.source_ingestion.adapters import get_source_adapter
from backend.modules.source_ingestion.models import CircuitState, Source
from backend.modules.source_ingestion.repository import SourceRepository
from backend.modules.source_ingestion.schemas import SourceHealthResponse


def _unhealthy(source: Source) -> SourceHealthResponse:
    return SourceHealthResponse(
        source_id=source.id,
        status="unhealthy",
        failure_count=source.failure_count,
        success_count=source.success_count,
        circuit_state=source.circuit_state,
        negative_cache_until=source.negative_cache_until,
        last_success_at=source.last_success_at,
    )


async def collect_source_health(
    repo: SourceRepository,
    tenant_id: UUID,
) -> list[SourceHealthResponse]:
    sources = await repo.list_sources(tenant_id)

    async def _check(source: Source) -> SourceHealthResponse:
        try:
            connector_health = await get_source_adapter(source).healthcheck()
            status = connector_health.get("status", "healthy")
        except Exception:
            status = "unhealthy"
        if source.circuit_state == CircuitState.OPEN.value and source.negative_cache_until:
            status = "degraded"
        elif not source.active:
            status = "paused"
        response = _unhealthy(source)
        return response.model_copy(update={"status": status})

    outcomes = await map_concurrent(
        sources,
        _check,
        limit=max(1, settings.HTTP_INGESTION_HEALTH_CONCURRENCY),
        return_exceptions=True,
    )
    return [
        _unhealthy(sources[index]) if isinstance(outcome, Exception) else outcome
        for index, outcome in enumerate(outcomes)
    ]
