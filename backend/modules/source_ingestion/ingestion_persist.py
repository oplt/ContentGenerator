"""Persist accepted articles after network fetch (Transaction B helpers)."""

from __future__ import annotations

from contextlib import nullcontext
from uuid import UUID

from backend.core.domain_metrics import domain_metrics
from backend.core.log_context import bind_log_context
from backend.core.time_utils import utc_now
from backend.modules.audit.service import AuditService
from backend.modules.source_ingestion.adapters import FetchedArticle, get_source_adapter, normalize_title
from backend.modules.source_ingestion.fetch_cache import build_article_token_index, save_cache
from backend.modules.source_ingestion.models import (
    CircuitState,
    FetchRunStatus,
    RawArticle,
    Source,
    SourceFetchRun,
    SourceHealthEvent,
)
from backend.modules.source_ingestion.repository import ArticleDedupeKeys, SourceRepository
from backend.modules.source_ingestion.scheduling import schedule_after_poll
from backend.modules.source_ingestion.schemas import IngestionTriggerResponse
from backend.modules.source_ingestion.service import SourceIngestionService


async def persist_success_body(
    *,
    db,
    source: Source,
    fetch_run: SourceFetchRun,
    fetched_articles: list[FetchedArticle],
    live_fetch_succeeded: bool,
    polled_at,
) -> tuple[IngestionTriggerResponse, list[UUID]]:
    """
    Short DB unit of work: dedupe + insert raw articles + finalize fetch run.

    Does **not** call Ollama. Caller runs clustering after this session commits.
    """
    from backend.modules.source_ingestion.ingestion_profile import (
        STAGE_DATABASE_READS,
        STAGE_DATABASE_WRITES,
        STAGE_DEDUPLICATION,
        get_ingestion_profiler,
    )

    bind_log_context(tenant_id=source.tenant_id, source_id=source.id, stage="persist")
    repo = SourceRepository(db)
    adapter = get_source_adapter(source)
    profiler = get_ingestion_profiler()

    def _stage(name: str):
        if profiler is not None:
            return profiler.stage(name)
        return nullcontext()

    with _stage(STAGE_DATABASE_READS):
        recent_articles = await repo.list_recent_raw_articles(tenant_id=source.tenant_id, within_hours=24)

    candidate_keys: list[ArticleDedupeKeys] = []
    prepared_articles: list[tuple[FetchedArticle, str, str]] = []
    with _stage(STAGE_DEDUPLICATION):
        for article in fetched_articles:
            dedupe_key = adapter.dedupe_key(article)
            title_normalized = normalize_title(article.title)
            candidate_keys.append(
                ArticleDedupeKeys(
                    canonical_url=article.canonical_url,
                    content_hash=article.content_hash,
                    dedupe_key=dedupe_key,
                    title_normalized=title_normalized,
                )
            )
            prepared_articles.append((article, dedupe_key, title_normalized))

        existing_by_index = await repo.find_existing_articles_batch(
            tenant_id=source.tenant_id,
            candidates=candidate_keys,
        )
        pending_inserts: list[RawArticle] = []
        service = SourceIngestionService(db)
        recent_token_index = build_article_token_index(recent_articles)
        for index, (article, dedupe_key, title_normalized) in enumerate(prepared_articles):
            if index in existing_by_index:
                continue
            if service._semantic_duplicate(article, recent_articles, token_index=recent_token_index):
                continue
            pending_inserts.append(
                RawArticle(
                    tenant_id=source.tenant_id,
                    source_id=source.id,
                    fetch_run_id=fetch_run.id,
                    url=article.url,
                    canonical_url=article.canonical_url,
                    dedupe_key=dedupe_key,
                    title_normalized=title_normalized,
                    content_hash=article.content_hash,
                    title=article.title,
                    summary=article.summary,
                    body=article.body,
                    author=article.author,
                    language=article.language or next(iter(source.language_tags), None),
                    published_at=article.published_at,
                    extraction_confidence=0.75,
                    source_metadata={
                        **article.metadata,
                        "category_tags": ",".join(article.category_tags),
                        "region_tags": ",".join(article.region_tags),
                        "raw_payload_present": "true" if article.raw_payload else "false",
                        **article.parser_diagnostics,
                    },
                )
            )

    with _stage(STAGE_DATABASE_WRITES):
        new_raw_articles = await repo.insert_raw_articles_conflict_safe(pending_inserts)
        duplicate_count = max(0, len(fetched_articles) - len(new_raw_articles))
        domain_metrics.record_ingestion(result="fetched", amount=len(fetched_articles))
        domain_metrics.record_ingestion(result="accepted", amount=len(new_raw_articles))
        domain_metrics.record_ingestion(result="duplicate", amount=duplicate_count)
        fetch_run.articles_found = len(fetched_articles)
        fetch_run.new_articles = len(new_raw_articles)
        fetch_run.finished_at = utc_now()
        if fetch_run.status == FetchRunStatus.RUNNING.value:
            fetch_run.status = FetchRunStatus.SUCCESS.value
        source.last_polled_at = polled_at
        source.next_poll_at = schedule_after_poll(
            polled_at=polled_at,
            polling_interval_minutes=source.polling_interval_minutes,
        )
        if live_fetch_succeeded:
            source.last_success_at = utc_now()
            source.success_count += 1
            source.failure_count = 0
            source.circuit_state = CircuitState.CLOSED.value
            source.negative_cache_until = None
            source.disabled_reason = None
            source.last_error = None
            source.trust_score = SourceIngestionService._recompute_trust_score(source)
            await save_cache(source, fetched_articles)
            await repo.create_health_event(
                SourceHealthEvent(
                    tenant_id=source.tenant_id,
                    source_id=source.id,
                    fetch_run_id=fetch_run.id,
                    status="healthy",
                    event_type="connector.fetch_succeeded",
                    message="Source polling succeeded",
                    details={
                        "articles_found": str(len(fetched_articles)),
                        "new_articles": str(len(new_raw_articles)),
                    },
                )
            )

    new_ids = [article.id for article in new_raw_articles]
    stage_timings = profiler.snapshot() if profiler is not None else {}
    await AuditService(db).record(
        tenant_id=source.tenant_id,
        actor_user_id=None,
        action="ingestion.source_polled",
        entity_type="source",
        entity_id=str(source.id),
        message=f"Source {source.name} polled",
        payload={
            "articles_found": len(fetched_articles),
            "new_articles": len(new_raw_articles),
            "connector": adapter.connector_name,
            "status": fetch_run.status,
            "stage_timings_ms": stage_timings,
        },
        payload_schema="ingestion.source_poll.v1",
        outcome=fetch_run.status,
    )
    if stage_timings:
        fetch_run.fetch_metadata = {
            **(fetch_run.fetch_metadata or {}),
            "stage_timings_ms": stage_timings,
        }
    await db.flush()
    response = IngestionTriggerResponse(
        source_id=source.id,
        status=fetch_run.status,
        raw_articles_ingested=len(new_raw_articles),
        clusters_updated=0,
        fetch_run_id=fetch_run.id,
    )
    return response, new_ids
