from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import UUID

from langdetect import detect  # type: ignore[import-untyped]
from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.service import AuditService
from backend.modules.content_strategy.repository import ContentStrategyRepository
from backend.modules.fact_review.service import FactRiskReviewService
from backend.modules.source_ingestion.enums import (
    ContentVertical,
    HIGH_RISK_VERTICALS,
    SourceTier,
    TIER_CREDIBILITY_WEIGHTS,
)
from backend.modules.source_ingestion.models import RawArticle, Source
from backend.modules.story_intelligence.models import (
    ClusterBlockReason,
    NormalizedArticle,
    RiskLevel,
    StoryCluster,
    StoryClusterArticle,
    TrendCandidate,
    TrendCandidateStatus,
    TrendWorkflowState,
    TrendScore,
)
from backend.modules.story_intelligence.providers import (
    cosine_similarity,
    get_embeddings_provider,
    get_llm_provider,
)
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository
from backend.modules.story_intelligence.scoring import ClusterScorer, STOPWORDS as SCORER_STOPWORDS
from backend.modules.story_intelligence.schemas import (
    ContentWorthinessDecision,
    NormalizedArticleResponse,
    StoryClusterDetailResponse,
    StoryClusterResponse,
    TrendCandidateResponse,
    TrendDashboardResponse,
    TrendScoreResponse,
)
from backend.modules.shared.schemas import SummaryMetric


STOPWORDS = SCORER_STOPWORDS


class StoryIntelligenceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = StoryIntelligenceRepository(db)
        self.strategy_repo = ContentStrategyRepository(db)
        self.audit = AuditService(db)
        self.llm = get_llm_provider()
        self.embeddings = get_embeddings_provider()
        self.fact_review = FactRiskReviewService()
        self.scorer = ClusterScorer(
            db, repo=self.repo, fact_review_service=self.fact_review, llm=self.llm
        )

    def _fact_review_service(self) -> FactRiskReviewService:
        if not hasattr(self, "fact_review") or self.fact_review is None:
            self.fact_review = FactRiskReviewService()
        return self.fact_review

    async def _sync_trend_candidate(
        self,
        *,
        cluster: StoryCluster,
        normalized_articles: list[NormalizedArticle],
        trend_score: TrendScore,
        blocked: bool,
    ) -> TrendCandidate:
        candidate = await self.repo.get_trend_candidate_for_cluster(cluster.tenant_id, cluster.id)
        source_mix = dict(Counter(article.source_tier for article in normalized_articles))
        supporting_item_ids = [str(article.id) for article in normalized_articles[:10]]
        evidence_links = [article.canonical_url for article in normalized_articles[:10] if article.canonical_url]
        extracted_claims: list[str] = []
        for article in normalized_articles[:5]:
            extracted_claims.extend(article.claims[:3])
        status = (
            TrendCandidateStatus.QUEUED_FOR_REVIEW.value
            if cluster.workflow_state == TrendWorkflowState.QUEUED_FOR_REVIEW.value
            else TrendCandidateStatus.NEW.value
        )
        topic_review = self._fact_review_service().review_topic(
            content_vertical=cluster.content_vertical or "general",
            headline=cluster.headline,
            summary=cluster.summary,
            claims=extracted_claims[:8],
            keywords=[keyword for article in normalized_articles for keyword in article.keywords[:4]],
        )
        if blocked and cluster.risk_level == RiskLevel.UNSAFE.value:
            status = TrendCandidateStatus.REJECTED_TOPIC.value
        expires_at = datetime.now(timezone.utc) + timedelta(hours=18)
        tier_breakdown = {
            "tier1": sum(1 for article in normalized_articles if article.source_tier == SourceTier.AUTHORITATIVE.value),
            "signal": sum(1 for article in normalized_articles if article.source_tier == SourceTier.SIGNAL.value),
            "amplification": sum(1 for article in normalized_articles if article.source_tier == SourceTier.AMPLIFICATION.value),
        }
        score_explanation = {
            "trend_score": trend_score.explanation,
            "cluster_explainability": cluster.explainability,
            "blocked": blocked,
            "risk_level": cluster.risk_level,
            "source_mix_breakdown": tier_breakdown,
            "contradiction_detected": self._has_contradiction(normalized_articles),
            "review_risk_label": topic_review["label"],
            "review_reasons": topic_review["reasons"],
            "topic_categories": topic_review["topic_categories"],
        }
        if candidate:
            candidate.date_bucket = datetime.now(timezone.utc).date()
            candidate.primary_topic = cluster.primary_topic
            candidate.subtopics = cluster.explainability.get("keywords", "").split(", ") if cluster.explainability.get("keywords") else []
            candidate.supporting_item_ids = supporting_item_ids
            candidate.evidence_links = evidence_links
            candidate.extracted_claims = extracted_claims
            candidate.cross_source_count = len({article.source_name for article in normalized_articles})
            candidate.source_mix = cast(dict[str, object], source_mix)
            candidate.velocity_score = trend_score.velocity_score
            candidate.recency_score = trend_score.freshness_score
            candidate.novelty_score = trend_score.novelty_score
            candidate.audience_fit_score = trend_score.audience_fit_score
            candidate.monetization_score = trend_score.monetization_score
            candidate.risk_score = trend_score.risk_penalty_score
            candidate.final_score = trend_score.score
            candidate.status = status
            candidate.expires_at = expires_at
            candidate.score_explanation = score_explanation
            await self.db.flush()
            return candidate
        return await self.repo.create_trend_candidate(
            TrendCandidate(
                tenant_id=cluster.tenant_id,
                story_cluster_id=cluster.id,
                date_bucket=datetime.now(timezone.utc).date(),
                primary_topic=cluster.primary_topic,
                subtopics=cluster.explainability.get("keywords", "").split(", ") if cluster.explainability.get("keywords") else [],
                supporting_item_ids=supporting_item_ids,
                evidence_links=evidence_links,
                extracted_claims=extracted_claims,
                cross_source_count=len({article.source_name for article in normalized_articles}),
                source_mix=cast(dict[str, object], source_mix),
                velocity_score=trend_score.velocity_score,
                recency_score=trend_score.freshness_score,
                novelty_score=trend_score.novelty_score,
                audience_fit_score=trend_score.audience_fit_score,
                monetization_score=trend_score.monetization_score,
                risk_score=trend_score.risk_penalty_score,
                final_score=trend_score.score,
                status=status,
                expires_at=expires_at,
                score_explanation=score_explanation,
            )
        )

    def _extract_keywords(self, text: str, limit: int = 8) -> list[str]:
        return self.scorer._extract_keywords(text, limit)


    def _infer_language(self, text: str) -> str:
        return self.scorer._infer_language(text)


    def _freshness_score(self, published_at: datetime | None) -> float:
        return self.scorer._freshness_score(published_at)


    def _risk_level(self, keywords: list[str]) -> RiskLevel:
        return self.scorer._risk_level(keywords)


    def _extract_claims(self, body: str, title: str) -> list[str]:
        return self.scorer._extract_claims(body, title)


    async def normalize_article(self, raw_article: RawArticle, source: Source) -> NormalizedArticle:
        existing = await self.repo.get_normalized_by_raw_article(raw_article.id)
        if existing:
            return existing
        body = raw_article.body or raw_article.summary or raw_article.title
        keywords = self._extract_keywords(f"{raw_article.title} {body}")
        topic_tags = keywords[:4]
        entities = [token.title() for token in topic_tags[:3]]
        language = raw_article.language or self._infer_language(body)
        embedding = await self.embeddings.embed(f"{raw_article.title}\n{body}")
        freshness_score = self._freshness_score(raw_article.published_at)
        # Apply tier weight multiplier to trust_score for tier-aware credibility
        tier_weight = TIER_CREDIBILITY_WEIGHTS.get(source.source_tier, 1.0)
        credibility_score = min(float(source.trust_score) * tier_weight, 1.0)
        worthiness_score = round((freshness_score * 0.4) + (credibility_score * 0.4) + min(len(keywords), 8) / 20, 4)

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
            claims=self._extract_claims(body, raw_article.title),
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

    def _has_contradiction(self, normalized_articles: list[NormalizedArticle]) -> bool:
        return self.scorer._has_contradiction(normalized_articles)


    def _is_high_risk_topic(self, cluster: StoryCluster, normalized_articles: list[NormalizedArticle]) -> bool:
        return self.scorer._is_high_risk_topic(cluster, normalized_articles)


    def _check_risk_gate(
        self, cluster: StoryCluster, normalized_articles: list[NormalizedArticle]
    ) -> tuple[bool, str | None]:
        return self.scorer._check_risk_gate(cluster, normalized_articles)


    def _load_score_weights(
        self,
        tenant_settings: dict[str, object] | None,
        brand_profile: Any = None,
    ) -> dict[str, float]:
        return self.scorer._load_score_weights(tenant_settings, brand_profile)


    def _heuristic_audience_fit(self, cluster: StoryCluster, articles: list[NormalizedArticle]) -> float:
        return self.scorer._heuristic_audience_fit(cluster, articles)


    def _heuristic_novelty(self, cluster: StoryCluster, velocity: float) -> float:
        return self.scorer._heuristic_novelty(cluster, velocity)


    def _heuristic_monetization(self, cluster: StoryCluster) -> float:
        return self.scorer._heuristic_monetization(cluster)


    async def _score_cluster(
        self,
        cluster: StoryCluster,
        normalized_articles: list[NormalizedArticle],
        tenant_settings: dict[str, object] | None = None,
        brand_profile: Any = None,
    ) -> tuple[TrendScore, ContentWorthinessDecision]:
        return await self.scorer._score_cluster(
            cluster, normalized_articles, tenant_settings, brand_profile
        )


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
                    risk_level=self._risk_level(normalized.keywords).value,
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
            trend_score, decision = await self._score_cluster(cluster, normalized_articles)
            # Risk gate: override decision for unsafe/risky/high-risk-vertical clusters
            blocked, block_reason = self._check_risk_gate(cluster, normalized_articles)
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
                    review_reasons=[reason.strip() for reason in cluster.explainability.get("review_reasons", "").split(",") if reason.strip()],
                    latest_trend_score=trend.score if trend else None,
                )
            )
        return responses

    async def list_trend_candidates(
        self,
        tenant_id: UUID,
        *,
        status: str | None = None,
        brand_profile_id: UUID | None = None,
        limit: int = 50,
    ) -> list[TrendCandidateResponse]:
        await self.expire_stale_candidates(tenant_id)
        brand_profile = None
        if brand_profile_id:
            brand_profile = await self.strategy_repo.get_brand_profile_by_id(tenant_id, brand_profile_id)
        candidates = await self.repo.list_trend_candidates(tenant_id, status=status, limit=limit)
        responses: list[TrendCandidateResponse] = []
        for candidate in candidates:
            if brand_profile:
                candidate.score_explanation = {
                    **candidate.score_explanation,
                    "brand_profile_id": str(brand_profile.id),
                }
            responses.append(TrendCandidateResponse.model_validate(candidate))
        return responses

    async def get_trend_candidate_detail(self, tenant_id: UUID, candidate_id: UUID) -> TrendCandidateResponse | None:
        await self.expire_stale_candidates(tenant_id)
        candidate = await self.repo.get_trend_candidate(tenant_id, candidate_id)
        if not candidate:
            return None
        return TrendCandidateResponse.model_validate(candidate)

    async def apply_candidate_action(
        self,
        *,
        tenant_id: UUID,
        candidate_id: UUID,
        action: str,
        operator_note: str | None = None,
    ) -> TrendCandidateResponse:
        await self.expire_stale_candidates(tenant_id)
        candidate = await self.repo.get_trend_candidate(tenant_id, candidate_id)
        if not candidate:
            raise ValueError("Trend candidate not found")
        cluster = await self.repo.get_cluster(tenant_id, candidate.story_cluster_id)
        normalized_action = action.lower()
        if normalized_action == "approve":
            candidate.status = TrendCandidateStatus.APPROVED_TOPIC.value
            if cluster:
                cluster.workflow_state = TrendWorkflowState.APPROVED_TOPIC.value
        elif normalized_action == "reject":
            candidate.status = TrendCandidateStatus.REJECTED_TOPIC.value
            if cluster:
                cluster.workflow_state = TrendWorkflowState.REJECTED.value
        elif normalized_action == "hold":
            candidate.status = TrendCandidateStatus.QUEUED_FOR_REVIEW.value
            if cluster:
                cluster.workflow_state = TrendWorkflowState.QUEUED_FOR_REVIEW.value
        else:
            raise ValueError(f"Unsupported candidate action: {action}")
        candidate.score_explanation = {
            **(candidate.score_explanation or {}),
            "operator_note": operator_note or "",
            "last_operator_action": normalized_action,
        }
        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=None,
            action="trend.candidate_actioned",
            entity_type="trend_candidate",
            entity_id=str(candidate.id),
            message=f"Trend candidate {normalized_action}",
            payload={"action": normalized_action, "operator_note": operator_note or ""},
            payload_schema="trend_candidate.action.v1",
        )
        await self.db.flush()
        return TrendCandidateResponse.model_validate(candidate)

    async def get_cluster_detail(self, tenant_id: UUID, cluster_id: UUID) -> StoryClusterDetailResponse | None:
        cluster = await self.repo.get_cluster(tenant_id, cluster_id)
        if not cluster:
            return None
        articles = await self.repo.list_normalized_for_cluster(cluster.id)
        trend = await self.repo.get_latest_trend_score(cluster.id)
        return StoryClusterDetailResponse(
            **cluster.__dict__,
            review_risk_label=cluster.explainability.get("review_risk_label"),
            review_reasons=[reason.strip() for reason in cluster.explainability.get("review_reasons", "").split(",") if reason.strip()],
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
            trend_score, decision = await self._score_cluster(
                cluster, normalized_articles, tenant_settings=tenant_settings
            )
            blocked, block_reason = self._check_risk_gate(cluster, normalized_articles)
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

    async def expire_stale_candidates(self, tenant_id: UUID) -> int:
        now = datetime.now(timezone.utc)
        candidates = await self.repo.list_trend_candidates(tenant_id, limit=500)
        count = 0
        for candidate in candidates:
            if candidate.status in {
                TrendCandidateStatus.APPROVED_TOPIC.value,
                TrendCandidateStatus.REJECTED_TOPIC.value,
                TrendCandidateStatus.EXPIRED.value,
            }:
                continue
            if candidate.expires_at and candidate.expires_at < now:
                candidate.status = TrendCandidateStatus.EXPIRED.value
                cluster = await self.repo.get_cluster(tenant_id, candidate.story_cluster_id)
                if cluster and cluster.workflow_state not in {
                    TrendWorkflowState.PUBLISHED.value,
                    TrendWorkflowState.REJECTED.value,
                }:
                    cluster.workflow_state = TrendWorkflowState.EXPIRED.value
                count += 1
        if count:
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
