"""Split-phase source ingestion: short DB sessions around network I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException

from backend.core.config import settings
from backend.core.time_utils import as_utc, utc_now
from backend.db.transactions import session_scope
from backend.modules.source_ingestion.adapters import FetchedArticle, get_source_adapter
from backend.modules.source_ingestion.fetch_cache import articles_from_cache, describe_fetch_error
from backend.modules.source_ingestion.ingestion_persist import persist_success_body as _persist_success_body
from backend.modules.source_ingestion.models import (
    CircuitState,
    FetchRunStatus,
    Source,
    SourceFetchRun,
    SourceHealthEvent,
)
from backend.modules.source_ingestion.repository import SourceRepository
from backend.modules.source_ingestion.schemas import IngestionTriggerResponse
from backend.modules.source_ingestion.service import SourceIngestionService


@dataclass(frozen=True, slots=True)
class PreparedIngestion:
    tenant_id: UUID
    source_id: UUID
    fetch_run_id: UUID
    source: Source


def _unbound_source_copy(source: Source) -> Source:
    """ORM-free copy safe to use after the prepare session closes."""
    return Source(
        id=source.id,
        tenant_id=source.tenant_id,
        name=source.name,
        source_type=source.source_type,
        url=source.url,
        parser_type=source.parser_type,
        category=source.category,
        category_tags=list(source.category_tags or []),
        region_tags=list(source.region_tags or []),
        language_tags=list(source.language_tags or []),
        source_tier=source.source_tier,
        content_vertical=source.content_vertical,
        freshness_decay_hours=source.freshness_decay_hours,
        legal_risk=source.legal_risk,
        rate_limit_rph=source.rate_limit_rph,
        tier1_confirmation_required=source.tier1_confirmation_required,
        config=dict(source.config or {}),
        polling_config=dict(source.polling_config or {}),
        parser_config=dict(source.parser_config or {}),
        polling_interval_minutes=source.polling_interval_minutes,
        trust_score=source.trust_score,
        active=source.active,
        robots_respected=source.robots_respected,
        failure_count=source.failure_count,
        success_count=source.success_count,
        circuit_state=source.circuit_state,
        negative_cache_until=source.negative_cache_until,
        last_polled_at=source.last_polled_at,
        next_poll_at=source.next_poll_at,
        last_success_at=source.last_success_at,
        disabled_reason=source.disabled_reason,
        last_error=source.last_error,
        stale_cache_ttl_seconds=source.stale_cache_ttl_seconds,
        version=source.version,
        created_at=source.created_at,
        updated_at=source.updated_at,
        deleted_at=source.deleted_at,
    )


async def prepare_ingestion(*, tenant_id: UUID, source_id: UUID) -> PreparedIngestion | IngestionTriggerResponse:
    """Transaction A: claim fetch run and snapshot source config."""
    async with session_scope() as db:
        service = SourceIngestionService(db)
        source = await service.get_source(tenant_id, source_id)
        now = utc_now()
        negative_cache_until = as_utc(source.negative_cache_until)
        if (
            source.circuit_state == CircuitState.OPEN.value
            and negative_cache_until is not None
            and negative_cache_until > now
        ):
            cached = await articles_from_cache(source)
            return IngestionTriggerResponse(
                source_id=source.id,
                status="circuit_open_using_cache" if cached else "circuit_open",
                raw_articles_ingested=0,
                clusters_updated=0,
            )

        adapter = get_source_adapter(source)
        fetch_run = await service.repo.create_fetch_run(
            SourceFetchRun(
                tenant_id=tenant_id,
                source_id=source.id,
                status=FetchRunStatus.RUNNING.value,
                started_at=now,
                fetch_metadata={
                    "connector": adapter.connector_name,
                    "rate_limit_policy": adapter.rate_limit_policy(),
                    "source_metadata": adapter.source_metadata(),
                },
            )
        )
        await db.flush()
        return PreparedIngestion(
            tenant_id=tenant_id,
            source_id=source.id,
            fetch_run_id=fetch_run.id,
            source=_unbound_source_copy(source),
        )


async def fetch_articles_outside_db(source: Source) -> tuple[list[FetchedArticle], bool, dict[str, str]]:
    """Network/robots/parse work — no DB session held."""
    adapter = get_source_adapter(source)
    articles = await adapter.normalize(await adapter.fetch())
    health = await adapter.healthcheck()
    return articles, True, health


async def persist_fetch_failure(
    *,
    prepared: PreparedIngestion,
    error_message: str,
) -> IngestionTriggerResponse:
    """Failure transaction: durable ledger + optional cache fallback signal."""
    async with session_scope() as db:
        repo = SourceRepository(db)
        source = await repo.get_source(prepared.tenant_id, prepared.source_id)
        fetch_run = await db.get(SourceFetchRun, prepared.fetch_run_id)
        if source is None or fetch_run is None:
            raise HTTPException(status_code=404, detail="Ingestion claim lost")

        now = utc_now()
        source.failure_count += 1
        if source.failure_count >= settings.INGESTION_DISABLE_AFTER_FAILURES:
            source.active = False
            source.disabled_reason = f"auto_disabled_after_{source.failure_count}_failures"
        source.trust_score = SourceIngestionService._recompute_trust_score(source)
        fetch_run.status = FetchRunStatus.FAILED.value
        fetch_run.error_message = error_message
        fetch_run.fetch_metadata = {**(fetch_run.fetch_metadata or {}), "exception": error_message}
        source.circuit_state = (
            CircuitState.OPEN.value if source.failure_count >= 3 else CircuitState.HALF_OPEN.value
        )
        source.negative_cache_until = now + timedelta(minutes=15)
        source.last_error = error_message
        await repo.create_health_event(
            SourceHealthEvent(
                tenant_id=source.tenant_id,
                source_id=source.id,
                fetch_run_id=fetch_run.id,
                status="failed",
                event_type="connector.fetch_failed",
                message="Connector fetch failed",
                details={"error": error_message},
            )
        )

        cached_articles = await articles_from_cache(source)
        if cached_articles:
            fetch_run.response_cache_hit = True
            fetch_run.status = FetchRunStatus.PARTIAL.value
            await repo.create_health_event(
                SourceHealthEvent(
                    tenant_id=source.tenant_id,
                    source_id=source.id,
                    fetch_run_id=fetch_run.id,
                    status="partial",
                    event_type="connector.cache_fallback",
                    message="Used stale cache after connector failure",
                    details={"cached_articles": str(len(cached_articles))},
                )
            )
            return await _persist_success_body(
                db=db,
                source=source,
                fetch_run=fetch_run,
                fetched_articles=cached_articles,
                live_fetch_succeeded=False,
                polled_at=now,
            )

        fetch_run.finished_at = utc_now()
        await db.flush()

    raise HTTPException(status_code=502, detail=f"Source fetch failed: {error_message}")


async def persist_fetch_success(
    *,
    prepared: PreparedIngestion,
    fetched_articles: list[FetchedArticle],
    live_fetch_succeeded: bool,
    health: dict[str, str] | None = None,
) -> IngestionTriggerResponse:
    """Transaction B: dedupe, bulk insert, finalize fetch run."""
    async with session_scope() as db:
        repo = SourceRepository(db)
        source = await repo.get_source(prepared.tenant_id, prepared.source_id)
        fetch_run = await db.get(SourceFetchRun, prepared.fetch_run_id)
        if source is None or fetch_run is None:
            raise HTTPException(status_code=404, detail="Ingestion claim lost")
        if health:
            fetch_run.fetch_metadata = {**(fetch_run.fetch_metadata or {}), "healthcheck": health}
            await repo.create_health_event(
                SourceHealthEvent(
                    tenant_id=source.tenant_id,
                    source_id=source.id,
                    fetch_run_id=fetch_run.id,
                    status="healthy",
                    event_type="connector.healthcheck",
                    message="Connector healthcheck succeeded",
                    details=health,
                )
            )
        return await _persist_success_body(
            db=db,
            source=source,
            fetch_run=fetch_run,
            fetched_articles=fetched_articles,
            live_fetch_succeeded=live_fetch_succeeded,
            polled_at=fetch_run.started_at or utc_now(),
        )


async def run_ingestion_workflow(*, tenant_id: UUID, source_id: UUID) -> IngestionTriggerResponse:
    """
    Full split-phase ingestion.

    Prepare session commits+closes before network. Persist/failure use fresh sessions.
    """
    prepared = await prepare_ingestion(tenant_id=tenant_id, source_id=source_id)
    if isinstance(prepared, IngestionTriggerResponse):
        return prepared

    try:
        articles, live_ok, health = await fetch_articles_outside_db(prepared.source)
    except Exception as exc:
        return await persist_fetch_failure(
            prepared=prepared,
            error_message=describe_fetch_error(exc),
        )

    return await persist_fetch_success(
        prepared=prepared,
        fetched_articles=articles,
        live_fetch_succeeded=live_ok,
        health=health,
    )
