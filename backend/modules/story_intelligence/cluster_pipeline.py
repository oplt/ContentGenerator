"""Article normalization, clustering, and rescoring pipeline."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from slugify import slugify

from backend.modules.source_ingestion.enums import TIER_CREDIBILITY_WEIGHTS
from backend.modules.source_ingestion.models import RawArticle, Source
from backend.modules.story_intelligence.models import (
    NormalizedArticle,
    StoryCluster,
    StoryClusterArticle,
    TrendWorkflowState,
)
from backend.modules.story_intelligence.providers import cosine_similarity
from backend.modules.story_intelligence.schemas import (
    NormalizedArticleResponse,
    StoryClusterDetailResponse,
    StoryClusterResponse,
    TrendDashboardResponse,
    TrendScoreResponse,
)
from backend.modules.shared.schemas import SummaryMetric


class ClusterPipelineMixin:
    """Normalize articles, match clusters, score, and present cluster views."""

    async def normalize_article(self, raw_article: RawArticle, source: Source) -> NormalizedArticle:
        existing = await self.repo.get_normalized_by_raw_article(raw_article.id)
        if existing:
            return existing
        body = raw_article.body or raw_article.summary or raw_article.title
        keywords = self.scorer._extract_keywords(f"{raw_article.title} {body}")
        topic_tags = keywords[:4]
        entities = [token.title() for token in topic_tags[:3]]
        language = raw_article.language or self.scorer._infer_language(body)
        embedding = await self.embeddings.embed(f"{raw_article.title}\n{body}")
        freshness_score = self.scorer._freshness_score(raw_article.published_at)
        # Apply tier weight multiplier to trust_score for tier-aware credibility
        tier_weight = TIER_CREDIBILITY_WEIGHTS.get(source.source_tier, 1.0)
        credibility_score = min(float(source.trust_score) * tier_weight, 1.0)
        worthiness_score = round(
            (freshness_score * 0.4) + (credibility_score * 0.4) + min(len(keywords), 8) / 20, 4
        )

        # Semantic near-dedup: skip syndicated copies (cosine > 0.97 within 6h)
        near_dup = await self.repo.find_near_duplicate(
            raw_article.tenant_id, embedding, within_hours=6
        )
        if near_dup:
            return near_dup

        article = NormalizedArticle(
            tenant_id=raw_article.tenant_id,
            raw_article_id=raw_article.id,
            title=raw_article.title,
            summary=raw_article.summary,
            body=body,
            canonical_url=raw_article.canonical_url,
            source_name=source.name,
            language=language,
            published_at=raw_article.published_at,
            keywords=keywords,
            topic_tags=topic_tags,
            entities=entities,
            embedding=embedding,
            freshness_score=freshness_score,
            credibility_score=credibility_score,
            worthiness_score=worthiness_score,
            # Inherit classification from the source
            source_tier=source.source_tier,
            content_vertical=source.content_vertical,
            claims=self.scorer._extract_claims(body, raw_article.title),
            explainability={
                "keywords": ", ".join(keywords[:5]),
                "freshness_score": f"{freshness_score:.2f}",
                "credibility_score": f"{credibility_score:.2f}",
                "source_tier": source.source_tier,
                "content_vertical": source.content_vertical,
            },
        )
        return await self.repo.create_normalized_article(article)

    async def _find_cluster_match(
        self,
        *,
        tenant_id: UUID,
        normalized_article: NormalizedArticle,
    ) -> StoryCluster | None:
        recent_clusters = await self.repo.list_recent_clusters(tenant_id)
        article_embedding: list[float] = normalized_article.embedding or []
        for cluster in recent_clusters:
            cluster_keywords = set(cluster.explainability.get("keywords", "").split(", "))
            overlap = len(cluster_keywords.intersection(normalized_article.topic_tags))
            cluster_embedding: list[float] = cluster.embedding or []
            similarity = (
                cosine_similarity(article_embedding, cluster_embedding)
                if cluster_embedding and article_embedding
                else 0.0
            )
            # Semantic similarity threshold lowered slightly to 0.82 since real embeddings
            # have more resolution than hashing vectors.
            if overlap >= 2 or similarity >= 0.82:
                return cluster
        return None

    async def process_articles(self, *, source: Source, raw_articles: list[RawArticle]) -> list[StoryCluster]:
        clusters: list[StoryCluster] = []
        for raw_article in raw_articles:
            normalized = await self.normalize_article(raw_article, source)
            cluster = await self._find_cluster_match(
                tenant_id=raw_article.tenant_id,
                normalized_article=normalized,
            )
            if not cluster:
                summary = await self.llm.summarize(f"{normalized.title}\n{normalized.body}", max_words=60)
                cluster = StoryCluster(
                    tenant_id=raw_article.tenant_id,
                    slug=slugify(normalized.title)[:255],
                    headline=normalized.title,
                    summary=summary,
                    primary_topic=normalized.topic_tags[0] if normalized.topic_tags else "general",
                    representative_article_id=normalized.id,
                    article_count=0,
                    trend_direction="up",
                    worthy_for_content=False,
                    risk_level=self.scorer._risk_level(normalized.keywords).value,
                    content_vertical=normalized.content_vertical,
                    embedding=normalized.embedding,
                    explainability={
                        "keywords": ", ".join(normalized.topic_tags),
                        "content_vertical": normalized.content_vertical,
                    },
                )
                cluster = await self.repo.create_cluster(cluster)
            cluster.article_count += 1
            await self.repo.add_cluster_article(
                StoryClusterArticle(
                    story_cluster_id=cluster.id,
                    normalized_article_id=normalized.id,
                    rank=cluster.article_count,
                    is_primary=cluster.article_count == 1,
                )
            )
            normalized_articles = await self.repo.list_normalized_for_cluster(cluster.id)
            trend_score, decision = await self.scorer._score_cluster(cluster, normalized_articles)
            # Risk gate: override decision for unsafe/risky/high-risk-vertical clusters
            blocked, block_reason = self.scorer._check_risk_gate(cluster, normalized_articles)
            cluster.worthy_for_content = (decision.decision == "generate") and not blocked
            cluster.workflow_state = (
                TrendWorkflowState.QUEUED_FOR_REVIEW.value
                if cluster.worthy_for_content
                else TrendWorkflowState.NEW.value
            )
            cluster.explainability["score"] = f"{decision.score:.2f}"
            if blocked:
                cluster.explainability["blocked"] = block_reason or "risk_gate"
            await self.repo.create_trend_score(trend_score)
            candidate = await self._sync_trend_candidate(
                cluster=cluster,
                normalized_articles=normalized_articles,
                trend_score=trend_score,
                blocked=blocked,
            )
            await self.audit.record(
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
            clusters.append(cluster)
        await self.db.flush()
        return clusters

    async def list_clusters(self, tenant_id: UUID, worthy_only: bool = False) -> list[StoryClusterResponse]:
        clusters = await self.repo.list_clusters(tenant_id=tenant_id, worthy_only=worthy_only)
        responses: list[StoryClusterResponse] = []
        for cluster in clusters:
            trend = await self.repo.get_latest_trend_score(cluster.id)
            responses.append(
                StoryClusterResponse(
                    **cluster.__dict__,
                    review_risk_label=cluster.explainability.get("review_risk_label"),
                    review_reasons=[
                        reason.strip()
                        for reason in cluster.explainability.get("review_reasons", "").split(",")
                        if reason.strip()
                    ],
                    latest_trend_score=trend.score if trend else None,
                )
            )
        return responses

    async def get_cluster_detail(self, tenant_id: UUID, cluster_id: UUID) -> StoryClusterDetailResponse | None:
        cluster = await self.repo.get_cluster(tenant_id, cluster_id)
        if not cluster:
            return None
        articles = await self.repo.list_normalized_for_cluster(cluster.id)
        trend = await self.repo.get_latest_trend_score(cluster.id)
        return StoryClusterDetailResponse(
            **cluster.__dict__,
            review_risk_label=cluster.explainability.get("review_risk_label"),
            review_reasons=[
                reason.strip()
                for reason in cluster.explainability.get("review_reasons", "").split(",")
                if reason.strip()
            ],
            articles=[NormalizedArticleResponse.model_validate(article) for article in articles],
            trend_score=TrendScoreResponse.model_validate(trend) if trend else None,
            latest_trend_score=trend.score if trend else None,
        )

    async def rescore_active_clusters(self, tenant_id: UUID) -> int:
        """Re-score all active clusters for a tenant. Called by Celery beat every 15 min."""
        # Load per-tenant weight overrides so rescore respects the same weights as live scoring
        tenant_settings: dict[str, object] | None = None
        try:
            from backend.modules.settings.service import SettingsService
            settings_svc = SettingsService(self.db)
            tenant_obj = await settings_svc.get_tenant_settings(tenant_id)
            tenant_settings = cast(dict[str, object] | None, tenant_obj.settings if tenant_obj else None)
        except Exception:
            pass  # Fall back to defaults if settings are unavailable

        clusters = await self.repo.list_clusters(tenant_id=tenant_id, worthy_only=False)
        count = 0
        for cluster in clusters:
            normalized_articles = await self.repo.list_normalized_for_cluster(cluster.id)
            if not normalized_articles:
                continue
            trend_score, decision = await self.scorer._score_cluster(
                cluster, normalized_articles, tenant_settings=tenant_settings
            )
            blocked, block_reason = self.scorer._check_risk_gate(cluster, normalized_articles)
            cluster.worthy_for_content = (decision.decision == "generate") and not blocked
            cluster.workflow_state = (
                TrendWorkflowState.QUEUED_FOR_REVIEW.value
                if cluster.worthy_for_content
                else TrendWorkflowState.NEW.value
            )
            cluster.explainability["score"] = f"{decision.score:.2f}"
            if blocked:
                cluster.explainability["blocked"] = block_reason or "risk_gate"
            await self.repo.create_trend_score(trend_score)
            await self._sync_trend_candidate(
                cluster=cluster,
                normalized_articles=normalized_articles,
                trend_score=trend_score,
                blocked=blocked,
            )
            count += 1
        await self.db.flush()
        return count

    async def trend_dashboard(self, tenant_id: UUID) -> TrendDashboardResponse:
        clusters = await self.list_clusters(tenant_id=tenant_id, worthy_only=False)
        worthy = [cluster for cluster in clusters if cluster.worthy_for_content]
        avg_score = (
            sum(cluster.latest_trend_score or 0.0 for cluster in clusters) / len(clusters)
            if clusters
            else 0.0
        )
        return TrendDashboardResponse(
            summary=[
                SummaryMetric(key="clusters", label="Active clusters", value=len(clusters)),
                SummaryMetric(key="worthy", label="Content-worthy", value=len(worthy)),
                SummaryMetric(key="avg_score", label="Average score", value=round(avg_score, 2)),
            ],
            clusters=clusters[:12],
        )
