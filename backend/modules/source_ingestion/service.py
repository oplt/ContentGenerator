from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import RetryError

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.core.time_utils import as_utc, utc_now
from backend.modules.audit.service import AuditService
from backend.modules.source_ingestion.adapters import (
    FetchedArticle,
    get_source_adapter,
    normalize_title,
    tokenize_for_similarity,
)
from backend.modules.source_ingestion.models import (
    CircuitState,
    FetchRunStatus,
    RawArticle,
    Source,
    SourceFetchRun,
    SourceHealthEvent,
)
from backend.modules.source_ingestion.repository import SourceRepository
from backend.modules.source_ingestion.schemas import (
    IngestionTriggerResponse,
    SourceActionResponse,
    SourceCreateRequest,
    SourceHealthResponse,
    SourceUpdateRequest,
)
from backend.modules.story_intelligence.service import StoryIntelligenceService


class SourceIngestionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = SourceRepository(db)
        self.audit = AuditService(db)

    @staticmethod
    def _recompute_trust_score(source: Source) -> float:
        """
        Blend the user-set baseline with observed reliability.
        baseline * 0.5 + consistency * 0.3 + longevity * 0.2
        consistency = success_count / (success_count + failure_count)
        longevity   = 1 - failure_rate (same denominator, inverse)
        """
        total = source.success_count + source.failure_count
        if total == 0:
            return source.trust_score
        consistency = source.success_count / total
        longevity = 1.0 - (source.failure_count / total)
        computed = (source.trust_score * 0.5) + (consistency * 0.3) + (longevity * 0.2)
        return round(min(max(computed, 0.0), 1.0), 4)

    async def create_source(self, tenant_id: UUID, payload: SourceCreateRequest) -> Source:
        source = Source(tenant_id=tenant_id, **payload.model_dump())
        return await self.repo.create_source(source)

    async def update_source(self, tenant_id: UUID, source_id: UUID, payload: SourceUpdateRequest) -> Source:
        source = await self.repo.get_source(tenant_id, source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        for key, value in payload.model_dump(exclude_none=True).items():
            setattr(source, key, value)
        await self.db.flush()
        return source

    async def disable_source(self, tenant_id: UUID, source_id: UUID, reason: str = "disabled_by_operator") -> SourceActionResponse:
        source = await self.get_source(tenant_id, source_id)
        source.active = False
        source.disabled_reason = reason
        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=None,
            action="ingestion.source_disabled",
            entity_type="source",
            entity_id=str(source.id),
            message=f"Source {source.name} disabled",
            payload={"reason": reason},
        )
        await self.db.flush()
        return SourceActionResponse(source_id=source.id, status="disabled", detail=reason)

    async def delete_source(self, tenant_id: UUID, source_id: UUID) -> None:
        source = await self.repo.get_source(tenant_id, source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        await self.repo.hard_delete_source(source)
        await redis_client.delete(f"ingestion:source:{source.id}:last_success")
        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=None,
            action="ingestion.source_deleted",
            entity_type="source",
            entity_id=str(source.id),
            message=f"Source {source.name} deleted",
            payload={"source_type": str(source.source_type), "url": source.url},
        )
        await self.db.flush()

    async def list_sources(self, tenant_id: UUID) -> list[Source]:
        return await self.repo.list_sources(tenant_id)

    async def get_source(self, tenant_id: UUID, source_id: UUID) -> Source:
        source = await self.repo.get_source(tenant_id, source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        return source

    async def list_raw_articles(self, tenant_id: UUID) -> list[RawArticle]:
        return await self.repo.list_raw_articles(tenant_id=tenant_id)

    async def list_fetch_runs(self, tenant_id: UUID) -> list[SourceFetchRun]:
        return await self.repo.list_fetch_runs(tenant_id=tenant_id)

    async def _record_health_event(
        self,
        *,
        source: Source,
        fetch_run: SourceFetchRun | None,
        status: str,
        event_type: str,
        message: str,
        details: dict[str, str] | None = None,
    ) -> None:
        await self.repo.create_health_event(
            SourceHealthEvent(
                tenant_id=source.tenant_id,
                source_id=source.id,
                fetch_run_id=fetch_run.id if fetch_run else None,
                status=status,
                event_type=event_type,
                message=message,
                details=details or {},
            )
        )

    async def source_health(self, tenant_id: UUID) -> list[SourceHealthResponse]:
        sources = await self.repo.list_sources(tenant_id)
        health_items: list[SourceHealthResponse] = []
        for source in sources:
            adapter = get_source_adapter(source)
            connector_health = await adapter.healthcheck()
            if source.circuit_state == CircuitState.OPEN.value and source.negative_cache_until:
                status = "degraded"
            elif not source.active:
                status = "paused"
            else:
                status = connector_health.get("status", "healthy")
            health_items.append(
                SourceHealthResponse(
                    source_id=source.id,
                    status=status,
                    failure_count=source.failure_count,
                    success_count=source.success_count,
                    circuit_state=source.circuit_state,
                    negative_cache_until=source.negative_cache_until,
                    last_success_at=source.last_success_at,
                )
            )
        return health_items

    def _semantic_duplicate(self, candidate: FetchedArticle, recent_articles: list[RawArticle]) -> RawArticle | None:
        candidate_tokens = tokenize_for_similarity(f"{candidate.title} {candidate.summary or ''}")
        if not candidate_tokens:
            return None
        for existing in recent_articles:
            existing_tokens = tokenize_for_similarity(f"{existing.title} {existing.summary or ''}")
            if not existing_tokens:
                continue
            overlap = len(candidate_tokens & existing_tokens)
            union = len(candidate_tokens | existing_tokens) or 1
            if overlap / union >= 0.88:
                return existing
        return None

    async def _articles_from_cache(self, source: Source) -> list[FetchedArticle]:
        cache_key = f"ingestion:source:{source.id}:last_success"
        cached = await redis_client.get(cache_key)
        if not cached:
            return []
        import json

        payload = json.loads(cached)
        articles: list[FetchedArticle] = []
        for item in payload:
            articles.append(
                FetchedArticle(
                    url=item["url"],
                    canonical_url=item["canonical_url"],
                    title=item["title"],
                    summary=item.get("summary"),
                    body=item.get("body"),
                    author=item.get("author"),
                    published_at=None,
                    metadata=item.get("metadata", {}),
                )
            )
        return articles

    async def _save_cache(self, source: Source, articles: list[FetchedArticle]) -> None:
        cache_key = f"ingestion:source:{source.id}:last_success"
        import json

        payload = [
            {
                "url": article.url,
                "canonical_url": article.canonical_url,
                "title": article.title,
                "summary": article.summary,
                "body": article.body,
                "author": article.author,
                "metadata": article.metadata,
            }
            for article in articles
        ]
        await redis_client.setex(cache_key, source.stale_cache_ttl_seconds, json.dumps(payload))

    def _describe_fetch_error(self, exc: Exception) -> str:
        if isinstance(exc, RetryError):
            last_error = exc.last_attempt.exception()
            if last_error:
                return str(last_error)
        return str(exc)

    async def run_ingestion(self, tenant_id: UUID, source_id: UUID) -> IngestionTriggerResponse:
        source = await self.get_source(tenant_id, source_id)
        now = utc_now()
        live_fetch_succeeded = False
        if (
            source.circuit_state == CircuitState.OPEN.value
            and source.negative_cache_until
            and as_utc(source.negative_cache_until) > now
        ):
            cached = await self._articles_from_cache(source)
            return IngestionTriggerResponse(
                source_id=source.id,
                status="circuit_open_using_cache" if cached else "circuit_open",
                raw_articles_ingested=0,
                clusters_updated=0,
            )

        fetch_run = await self.repo.create_fetch_run(
            SourceFetchRun(
                tenant_id=tenant_id,
                source_id=source.id,
                status=FetchRunStatus.RUNNING.value,
                started_at=now,
            )
        )
        adapter = get_source_adapter(source)
        fetch_run.fetch_metadata = {
            "connector": adapter.connector_name,
            "rate_limit_policy": adapter.rate_limit_policy(),
            "source_metadata": adapter.source_metadata(),
        }
        fetched_articles: list[FetchedArticle] = []
        try:
            fetched_articles = await adapter.normalize(await adapter.fetch())
            live_fetch_succeeded = True
            health = await adapter.healthcheck()
            fetch_run.fetch_metadata = {
                **fetch_run.fetch_metadata,
                "healthcheck": health,
            }
            await self._record_health_event(
                source=source,
                fetch_run=fetch_run,
                status="healthy",
                event_type="connector.healthcheck",
                message="Connector healthcheck succeeded",
                details=health,
            )
        except Exception as exc:
            error_message = self._describe_fetch_error(exc)
            source.failure_count += 1
            if source.failure_count >= settings.INGESTION_DISABLE_AFTER_FAILURES:
                source.active = False
                source.disabled_reason = f"auto_disabled_after_{source.failure_count}_failures"
            source.trust_score = self._recompute_trust_score(source)
            fetch_run.status = FetchRunStatus.FAILED.value
            fetch_run.error_message = error_message
            fetch_run.fetch_metadata = {
                **fetch_run.fetch_metadata,
                "exception": error_message,
            }
            source.circuit_state = (
                CircuitState.OPEN.value if source.failure_count >= 3 else CircuitState.HALF_OPEN.value
            )
            source.negative_cache_until = now + timedelta(minutes=15)
            source.last_error = error_message
            await self._record_health_event(
                source=source,
                fetch_run=fetch_run,
                status="failed",
                event_type="connector.fetch_failed",
                message="Connector fetch failed",
                details={"error": error_message},
            )
            cached_articles = await self._articles_from_cache(source)
            if cached_articles:
                fetched_articles = cached_articles
                fetch_run.response_cache_hit = True
                fetch_run.status = FetchRunStatus.PARTIAL.value
                await self._record_health_event(
                    source=source,
                    fetch_run=fetch_run,
                    status="partial",
                    event_type="connector.cache_fallback",
                    message="Used stale cache after connector failure",
                    details={"cached_articles": str(len(cached_articles))},
                )
            else:
                fetch_run.finished_at = utc_now()
                await self.db.commit()
                raise HTTPException(status_code=502, detail=f"Source fetch failed: {error_message}") from exc

        new_raw_articles: list[RawArticle] = []
        recent_articles = await self.repo.list_recent_raw_articles(tenant_id=tenant_id, within_hours=24)
        for article in fetched_articles:
            dedupe_key = adapter.dedupe_key(article)
            title_normalized = normalize_title(article.title)
            existing = await self.repo.get_existing_article(
                tenant_id=tenant_id,
                canonical_url=article.canonical_url,
                content_hash=article.content_hash,
                dedupe_key=dedupe_key,
                title_normalized=title_normalized,
            )
            if existing:
                continue
            if self._semantic_duplicate(article, recent_articles):
                continue
            raw_article = await self.repo.create_raw_article(
                RawArticle(
                    tenant_id=tenant_id,
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
            new_raw_articles.append(raw_article)
            recent_articles.insert(0, raw_article)

        fetch_run.articles_found = len(fetched_articles)
        fetch_run.new_articles = len(new_raw_articles)
        fetch_run.finished_at = utc_now()
        if fetch_run.status == FetchRunStatus.RUNNING.value:
            fetch_run.status = FetchRunStatus.SUCCESS.value
        source.last_polled_at = now
        if live_fetch_succeeded:
            source.last_success_at = utc_now()
            source.success_count += 1
            source.failure_count = 0
            source.circuit_state = CircuitState.CLOSED.value
            source.negative_cache_until = None
            source.disabled_reason = None
            source.last_error = None
            source.trust_score = self._recompute_trust_score(source)
            await self._save_cache(source, fetched_articles)
            await self._record_health_event(
                source=source,
                fetch_run=fetch_run,
                status="healthy",
                event_type="connector.fetch_succeeded",
                message="Source polling succeeded",
                details={
                    "articles_found": str(len(fetched_articles)),
                    "new_articles": str(len(new_raw_articles)),
                },
            )

        intelligence_service = StoryIntelligenceService(self.db)
        clusters = await intelligence_service.process_articles(source=source, raw_articles=new_raw_articles)
        await self.audit.record(
            tenant_id=tenant_id,
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
            },
            payload_schema="ingestion.source_poll.v1",
            outcome=fetch_run.status,
        )
        await self.db.commit()
        return IngestionTriggerResponse(
            source_id=source.id,
            status=fetch_run.status,
            raw_articles_ingested=len(new_raw_articles),
            clusters_updated=len({cluster.id for cluster in clusters}),
        )

    async def trigger_manual_poll(self, tenant_id: UUID, source_id: UUID) -> IngestionTriggerResponse:
        return await self.run_ingestion(tenant_id, source_id)

    async def poll_due_sources(self) -> list[IngestionTriggerResponse]:
        import structlog
        log = structlog.get_logger(__name__)
        results: list[IngestionTriggerResponse] = []
        for source in await self.repo.list_due_sources():
            try:
                result = await self.run_ingestion(source.tenant_id, source.id)
                results.append(result)
            except Exception:
                log.exception("source_poll_failed", source_id=str(source.id), tenant_id=str(source.tenant_id))
                await self.db.rollback()
        return results
