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
    celery_task_id: str | None = None
    correlation_id: str | None = None


def _meta_str(metadata: dict[str, object] | None, key: str) -> str | None:
    if not metadata:
        return None
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


def _stamp_task_id(
    response: IngestionTriggerResponse,
    *,
    celery_task_id: str | None,
) -> IngestionTriggerResponse:
    """Ensure Celery task id is present on API/worker result payloads."""
    if celery_task_id and not response.task_id:
        response.task_id = celery_task_id
    return response


def _merge_trace_metadata(
    existing: dict[str, object] | None,
    *,
    celery_task_id: str | None,
    correlation_id: str | None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    merged: dict[str, object] = dict(existing or {})
    if extra:
        merged.update(extra)
    if celery_task_id:
        merged["celery_task_id"] = celery_task_id
    if correlation_id:
        merged["correlation_id"] = correlation_id
    return merged


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


async def prepare_ingestion(
    *,
    tenant_id: UUID,
    source_id: UUID,
    fetch_run_id: UUID | None = None,
    celery_task_id: str | None = None,
    correlation_id: str | None = None,
) -> PreparedIngestion | IngestionTriggerResponse:
    """Transaction A: claim fetch run and snapshot source config."""
    async with session_scope() as db:
        service = SourceIngestionService(db)
        source = await service.get_source(tenant_id, source_id)
        now = utc_now()
        fetch_run: SourceFetchRun | None = None
        if fetch_run_id is not None:
            fetch_run = await service.repo.get_fetch_run(
                tenant_id=tenant_id,
                source_id=source_id,
                fetch_run_id=fetch_run_id,
            )
            if fetch_run is None:
                raise HTTPException(status_code=404, detail="Ingestion run not found")
            if fetch_run.status != FetchRunStatus.QUEUED.value:
                existing_task = celery_task_id or _meta_str(
                    fetch_run.fetch_metadata, "celery_task_id"
                )
                return _stamp_task_id(
                    IngestionTriggerResponse(
                        source_id=source.id,
                        status=f"already_{fetch_run.status}",
                        raw_articles_ingested=fetch_run.new_articles,
                        clusters_updated=0,
                        fetch_run_id=fetch_run.id,
                        task_id=existing_task,
                    ),
                    celery_task_id=existing_task,
                )
        negative_cache_until = as_utc(source.negative_cache_until)
        if (
            source.circuit_state == CircuitState.OPEN.value
            and negative_cache_until is not None
            and negative_cache_until > now
        ):
            cached = await articles_from_cache(source)
            existing_task = celery_task_id or (
                _meta_str(fetch_run.fetch_metadata, "celery_task_id") if fetch_run else None
            )
            return _stamp_task_id(
                IngestionTriggerResponse(
                    source_id=source.id,
                    status="circuit_open_using_cache" if cached else "circuit_open",
                    raw_articles_ingested=0,
                    clusters_updated=0,
                    fetch_run_id=fetch_run.id if fetch_run else None,
                    task_id=existing_task,
                ),
                celery_task_id=existing_task,
            )

        adapter = get_source_adapter(source)
        resolved_task_id = celery_task_id
        resolved_correlation = correlation_id
        if fetch_run is None:
            resolved_task_id = celery_task_id
            fetch_run = await service.repo.create_fetch_run(
                SourceFetchRun(
                    tenant_id=tenant_id,
                    source_id=source.id,
                    status=FetchRunStatus.RUNNING.value,
                    started_at=now,
                    fetch_metadata=_merge_trace_metadata(
                        None,
                        celery_task_id=resolved_task_id,
                        correlation_id=resolved_correlation,
                        extra={
                            "connector": adapter.connector_name,
                            "rate_limit_policy": adapter.rate_limit_policy(),
                            "source_metadata": adapter.source_metadata(),
                            "trigger": "scheduler" if celery_task_id else "direct",
                        },
                    ),
                )
            )
        else:
            resolved_task_id = celery_task_id or _meta_str(
                fetch_run.fetch_metadata, "celery_task_id"
            )
            resolved_correlation = correlation_id or _meta_str(
                fetch_run.fetch_metadata, "correlation_id"
            )
            fetch_run.status = FetchRunStatus.RUNNING.value
            fetch_run.started_at = now
            fetch_run.fetch_metadata = _merge_trace_metadata(
                fetch_run.fetch_metadata,
                celery_task_id=resolved_task_id,
                correlation_id=resolved_correlation,
                extra={
                    "connector": adapter.connector_name,
                    "rate_limit_policy": adapter.rate_limit_policy(),
                    "source_metadata": adapter.source_metadata(),
                },
            )
        await db.flush()
        from backend.core.log_context import bind_log_context

        bind_log_context(
            tenant_id=tenant_id,
            source_id=source.id,
            fetch_run_id=fetch_run.id,
            celery_task_id=resolved_task_id,
            correlation_id=resolved_correlation,
        )
        return PreparedIngestion(
            tenant_id=tenant_id,
            source_id=source.id,
            fetch_run_id=fetch_run.id,
            source=_unbound_source_copy(source),
            celery_task_id=resolved_task_id,
            correlation_id=resolved_correlation,
        )


async def fetch_articles_outside_db(source: Source) -> tuple[list[FetchedArticle], bool, dict[str, str]]:
    """Network/robots/parse work — no DB session held."""
    from backend.modules.source_ingestion.ingestion_profile import (
        STAGE_NORMALIZATION,
        STAGE_PARSING,
        STAGE_SOURCE_FETCH,
        get_ingestion_profiler,
    )

    adapter = get_source_adapter(source)
    profiler = get_ingestion_profiler()
    if profiler is not None:
        with profiler.stage(STAGE_SOURCE_FETCH):
            raw = await adapter.fetch()
        with profiler.stage(STAGE_PARSING):
            # Adapter-level normalize covers parse cleanup + in-batch dedupe keys.
            articles = await adapter.normalize(raw)
        with profiler.stage(STAGE_NORMALIZATION):
            health = await adapter.healthcheck()
        return articles, True, health
    articles = await adapter.normalize(await adapter.fetch())
    health = await adapter.healthcheck()
    return articles, True, health


async def run_ingestion_workflow(
    *,
    tenant_id: UUID,
    source_id: UUID,
    fetch_run_id: UUID | None = None,
    celery_task_id: str | None = None,
    correlation_id: str | None = None,
) -> IngestionTriggerResponse:
    """
    Full split-phase ingestion.

    Prepare commits before network fetch. Persist commits before clustering LLM.
    Enrichment opens its own short sessions around embed/summarize.
    """
    from backend.modules.source_ingestion.ingestion_profile import ingestion_profile_scope

    with ingestion_profile_scope() as profiler:
        prepared = await prepare_ingestion(
            tenant_id=tenant_id,
            source_id=source_id,
            fetch_run_id=fetch_run_id,
            celery_task_id=celery_task_id,
            correlation_id=correlation_id,
        )
        if isinstance(prepared, IngestionTriggerResponse):
            return _stamp_task_id(prepared, celery_task_id=celery_task_id)

        try:
            articles, live_ok, health = await fetch_articles_outside_db(prepared.source)
        except Exception as exc:
            return _stamp_task_id(
                await persist_fetch_failure(
                    prepared=prepared,
                    error_message=describe_fetch_error(exc),
                ),
                celery_task_id=prepared.celery_task_id or celery_task_id,
            )

        response = await persist_fetch_success(
            prepared=prepared,
            fetched_articles=articles,
            live_fetch_succeeded=live_ok,
            health=health,
        )
        # Attach stage timings to the fetch run metadata via a short follow-up is optional;
        # timings are already in metrics/logs. Snapshot kept for tests/callers.
        _ = profiler.snapshot()
        return _stamp_task_id(
            response,
            celery_task_id=prepared.celery_task_id or celery_task_id,
        )


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
            response, new_ids = await _persist_success_body(
                db=db,
                source=source,
                fetch_run=fetch_run,
                fetched_articles=cached_articles,
                live_fetch_succeeded=False,
                polled_at=now,
            )
        else:
            fetch_run.finished_at = utc_now()
            await db.flush()
            raise HTTPException(status_code=502, detail=f"Source fetch failed: {error_message}")

    return await _enrich_after_persist(
        tenant_id=prepared.tenant_id,
        source_id=prepared.source_id,
        response=response,
        raw_article_ids=new_ids,
    )


async def _enrich_after_persist(
    *,
    tenant_id: UUID,
    source_id: UUID,
    response: IngestionTriggerResponse,
    raw_article_ids: list[UUID],
) -> IngestionTriggerResponse:
    """Run clustering LLM after persist session commit/close."""
    if not raw_article_ids:
        return response
    from backend.modules.source_ingestion.ingestion_profile import (
        STAGE_CLUSTERING,
        get_ingestion_profiler,
    )
    from backend.modules.story_intelligence.cluster_enrichment import enrich_raw_articles_outside_db

    profiler = get_ingestion_profiler()
    if profiler is not None:
        with profiler.stage(STAGE_CLUSTERING):
            cluster_ids = await enrich_raw_articles_outside_db(
                tenant_id=tenant_id,
                source_id=source_id,
                raw_article_ids=raw_article_ids,
            )
    else:
        cluster_ids = await enrich_raw_articles_outside_db(
            tenant_id=tenant_id,
            source_id=source_id,
            raw_article_ids=raw_article_ids,
        )
    response.clusters_updated = len(set(cluster_ids))
    return response


async def persist_fetch_success(
    *,
    prepared: PreparedIngestion,
    fetched_articles: list[FetchedArticle],
    live_fetch_succeeded: bool,
    health: dict[str, str] | None = None,
) -> IngestionTriggerResponse:
    """Transaction B: dedupe, bulk insert, finalize fetch run — then enrich outside TX."""
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
        response, new_ids = await _persist_success_body(
            db=db,
            source=source,
            fetch_run=fetch_run,
            fetched_articles=fetched_articles,
            live_fetch_succeeded=live_fetch_succeeded,
            polled_at=fetch_run.started_at or utc_now(),
        )

    return await _enrich_after_persist(
        tenant_id=prepared.tenant_id,
        source_id=prepared.source_id,
        response=response,
        raw_article_ids=new_ids,
    )
