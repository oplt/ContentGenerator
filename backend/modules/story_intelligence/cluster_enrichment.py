"""Split-phase clustering: short DB sessions around Ollama embed/summarize."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from uuid import UUID

from slugify import slugify

from backend.core.config import settings
from backend.db.transactions import session_scope
from backend.modules.inference.enrichment_cache import cached_embedding, cached_summary
from backend.modules.inference.providers import get_embeddings_provider, get_llm_provider
from backend.modules.source_ingestion.models import RawArticle
from backend.modules.source_ingestion.repository import SourceRepository
from backend.modules.story_intelligence.models import (
    StoryCluster,
    StoryClusterArticle,
    TrendWorkflowState,
)
from backend.modules.story_intelligence.providers import cosine_similarity
from backend.modules.story_intelligence.service import StoryIntelligenceService


@dataclass(frozen=True, slots=True)
class _ClusterSnap:
    id: UUID
    keywords: set[str]
    embedding: list[float]


@dataclass(frozen=True, slots=True)
class _ArticleSnap:
    raw_id: UUID
    tenant_id: UUID
    title: str
    body: str
    source_id: UUID
    existing_normalized_id: UUID | None
    trust_score: float
    source_tier: str
    content_vertical: str
    source_name: str
    recent_clusters: tuple[_ClusterSnap, ...]


def _match_cluster(
    *,
    topic_tags: list[str],
    embedding: list[float],
    recent: tuple[_ClusterSnap, ...],
) -> UUID | None:
    for cluster in recent:
        overlap = len(cluster.keywords.intersection(topic_tags))
        similarity = (
            cosine_similarity(embedding, cluster.embedding)
            if cluster.embedding and embedding
            else 0.0
        )
        if overlap >= 2 or similarity >= 0.82:
            return cluster.id
    return None


async def _load_snap(*, tenant_id: UUID, source_id: UUID, raw_article_id: UUID) -> _ArticleSnap | None:
    async with session_scope() as db:
        svc = StoryIntelligenceService(db)
        source = await SourceRepository(db).get_source(tenant_id, source_id)
        raw = await db.get(RawArticle, raw_article_id)
        if source is None or raw is None or raw.tenant_id != tenant_id:
            return None
        existing = await svc.repo.get_normalized_by_raw_article(raw.id)
        recent_rows = await svc.repo.list_recent_clusters(tenant_id)
        recent = tuple(
            _ClusterSnap(
                id=row.id,
                keywords={
                    token
                    for token in (row.explainability or {}).get("keywords", "").split(", ")
                    if token
                },
                embedding=list(row.embedding or []),
            )
            for row in recent_rows
        )
        return _ArticleSnap(
            raw_id=raw.id,
            tenant_id=raw.tenant_id,
            title=raw.title,
            body=raw.body or raw.summary or raw.title,
            source_id=source.id,
            existing_normalized_id=existing.id if existing else None,
            trust_score=float(source.trust_score),
            source_tier=source.source_tier,
            content_vertical=source.content_vertical,
            source_name=source.name,
            recent_clusters=recent,
        )


async def _persist_enriched(
    *,
    snap: _ArticleSnap,
    embedding: list[float],
    matched_cluster_id: UUID | None,
    cluster_summary: str | None,
    reuse_normalized_id: UUID | None,
) -> UUID:
    async with session_scope() as db:
        svc = StoryIntelligenceService(db)
        source = await SourceRepository(db).get_source(snap.tenant_id, snap.source_id)
        raw = await db.get(RawArticle, snap.raw_id)
        if source is None or raw is None:
            raise RuntimeError("enrichment persist lost source/raw article")

        if reuse_normalized_id is not None:
            normalized = await svc.repo.get_normalized_by_id(snap.tenant_id, reuse_normalized_id)
            if normalized is None:
                normalized = await svc.normalize_article_from_prepared(
                    raw_article=raw, source=source, embedding=embedding
                )
        else:
            normalized = await svc.normalize_article_from_prepared(
                raw_article=raw, source=source, embedding=embedding
            )

        cluster: StoryCluster | None = None
        if matched_cluster_id is not None:
            cluster = await svc.repo.get_cluster(snap.tenant_id, matched_cluster_id)
        if cluster is None:
            cluster = StoryCluster(
                tenant_id=snap.tenant_id,
                slug=slugify(normalized.title)[:255],
                headline=normalized.title,
                summary=cluster_summary or (normalized.summary or normalized.title)[:500],
                primary_topic=normalized.topic_tags[0] if normalized.topic_tags else "general",
                representative_article_id=normalized.id,
                article_count=0,
                trend_direction="up",
                worthy_for_content=False,
                risk_level=svc.scorer._risk_level(normalized.keywords).value,
                content_vertical=normalized.content_vertical,
                embedding=normalized.embedding,
                explainability={
                    "keywords": ", ".join(normalized.topic_tags),
                    "content_vertical": normalized.content_vertical,
                },
            )
            cluster = await svc.repo.create_cluster(cluster)

        cluster.article_count += 1
        await svc.repo.add_cluster_article(
            StoryClusterArticle(
                story_cluster_id=cluster.id,
                normalized_article_id=normalized.id,
                rank=cluster.article_count,
                is_primary=cluster.article_count == 1,
            )
        )
        normalized_articles = await svc.repo.list_normalized_for_cluster(cluster.id)
        trend_score, decision = await svc.scorer._score_cluster(cluster, normalized_articles)
        blocked, block_reason = svc.scorer._check_risk_gate(cluster, normalized_articles)
        cluster.worthy_for_content = (decision.decision == "generate") and not blocked
        cluster.workflow_state = (
            TrendWorkflowState.QUEUED_FOR_REVIEW.value
            if cluster.worthy_for_content
            else TrendWorkflowState.NEW.value
        )
        cluster.explainability["score"] = f"{decision.score:.2f}"
        if blocked:
            cluster.explainability["blocked"] = block_reason or "risk_gate"
        await svc.repo.create_trend_score(trend_score)
        candidate = await svc._sync_trend_candidate(
            cluster=cluster,
            normalized_articles=normalized_articles,
            trend_score=trend_score,
            blocked=blocked,
        )
        await svc.audit.record(
            tenant_id=cluster.tenant_id,
            actor_user_id=None,
            action="trend.candidate_scored",
            entity_type="trend_candidate",
            entity_id=str(candidate.id),
            message="Trend candidate score persisted",
            payload={
                "story_cluster_id": str(cluster.id),
                "final_score": trend_score.score,
                "cross_source_count": candidate.cross_source_count,
                "status": candidate.status,
            },
            payload_schema="trend_candidate.score.v1",
            outcome="scored",
        )
        await db.flush()
        return cluster.id


async def enrich_raw_articles_outside_db(
    *,
    tenant_id: UUID,
    source_id: UUID,
    raw_article_ids: list[UUID],
) -> list[UUID]:
    """
    For each raw article: short read TX → Ollama outside → short write TX.

    Never holds a DB connection across embed/summarize.
    """
    cluster_ids: list[UUID] = []
    for raw_id in raw_article_ids:
        snap = await _load_snap(tenant_id=tenant_id, source_id=source_id, raw_article_id=raw_id)
        if snap is None:
            continue

        async def _embed(snap=snap) -> list[float]:
            return await get_embeddings_provider().embed(f"{snap.title}\n{snap.body}")

        embedding = await cached_embedding(
            tenant_id=snap.tenant_id,
            title=snap.title,
            body=snap.body,
            model=str(settings.EMBEDDINGS_MODEL),
            factory=_embed,
        )

        reuse_normalized_id = snap.existing_normalized_id
        if reuse_normalized_id is None:
            async with session_scope() as db:
                near = await StoryIntelligenceService(db).repo.find_near_duplicate(
                    snap.tenant_id, embedding, within_hours=6
                )
                if near is not None:
                    reuse_normalized_id = near.id

        from backend.modules.story_intelligence.scoring_heuristics import STOPWORDS

        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", f"{snap.title} {snap.body}".lower())
        topic_tags = [
            word for word, _ in Counter(t for t in tokens if t not in STOPWORDS).most_common(4)
        ]
        matched = _match_cluster(
            topic_tags=topic_tags,
            embedding=embedding,
            recent=snap.recent_clusters,
        )

        cluster_summary: str | None = None
        if matched is None and reuse_normalized_id is None:

            async def _summarize(snap=snap) -> str:
                return await get_llm_provider().summarize(
                    f"{snap.title}\n{snap.body}", max_words=60
                )

            cluster_summary = await cached_summary(
                tenant_id=snap.tenant_id,
                title=snap.title,
                body=snap.body,
                model=str(settings.LLM_MODEL),
                max_words=60,
                factory=_summarize,
            )

        cid = await _persist_enriched(
            snap=snap,
            embedding=embedding,
            matched_cluster_id=matched,
            cluster_summary=cluster_summary,
            reuse_normalized_id=reuse_normalized_id,
        )
        cluster_ids.append(cid)
    return cluster_ids
