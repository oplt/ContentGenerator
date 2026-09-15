"""Cluster worthiness scoring facade — heuristics + risk gates + weighted score."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.fact_review.service import FactRiskReviewService
from backend.modules.source_ingestion.enums import SourceTier, TIER_CREDIBILITY_WEIGHTS
from backend.modules.story_intelligence.models import NormalizedArticle, RiskLevel, StoryCluster, TrendScore
from backend.modules.story_intelligence.providers import get_llm_provider
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository
from backend.modules.story_intelligence.risk_gates import RiskGateMixin
from backend.modules.story_intelligence.schemas import ContentWorthinessDecision
from backend.modules.story_intelligence.scoring_heuristics import STOPWORDS, ScoringHeuristicsMixin

__all__ = ["STOPWORDS", "ClusterScorer"]


class ClusterScorer(ScoringHeuristicsMixin, RiskGateMixin):
    """Keyword/risk heuristics and cluster worthiness scoring."""

    # Default scoring weights — can be overridden per-tenant via tenant settings
    DEFAULT_SCORE_WEIGHTS: dict[str, float] = {
        "freshness": 0.20,
        "credibility": 0.15,
        "velocity": 0.25,
        "cross_source": 0.10,
        "worthiness": 0.08,
        "audience_fit": 0.10,
        "novelty": 0.07,
        "monetization": 0.05,
        "risk_penalty": 0.00,  # subtracted, not added
    }

    def __init__(
        self,
        db: AsyncSession,
        *,
        repo: StoryIntelligenceRepository,
        fact_review_service: FactRiskReviewService | None = None,
        llm: Any | None = None,
    ) -> None:
        self.db = db
        self.repo = repo
        self._fact_review = fact_review_service
        self.llm = llm or get_llm_provider()

    def _load_score_weights(
        self,
        tenant_settings: dict[str, object] | None,
        brand_profile: Any = None,
    ) -> dict[str, float]:
        """Load per-tenant score weights from settings, falling back to defaults."""
        weights = dict(self.DEFAULT_SCORE_WEIGHTS)
        if not tenant_settings:
            return weights
        import json as _json
        raw = tenant_settings.get("scoring.weights", "")
        if raw:
            try:
                overrides = _json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(overrides, dict):
                    for key, val in overrides.items():
                        if key in weights and isinstance(val, (int, float)):
                            weights[key] = float(val)
            except Exception:
                pass
        if brand_profile:
            overrides = ((brand_profile.guardrails or {}).get("scoring_weights")) or {}
            if isinstance(overrides, dict):
                for key, val in overrides.items():
                    if key in weights and isinstance(val, (int, float)):
                        weights[key] = float(val)
        return weights

    async def _score_cluster(
        self,
        cluster: StoryCluster,
        normalized_articles: list[NormalizedArticle],
        tenant_settings: dict[str, object] | None = None,
        brand_profile: Any = None,
    ) -> tuple[TrendScore, ContentWorthinessDecision]:
        article_count = len(normalized_articles)
        freshness = max((article.freshness_score for article in normalized_articles), default=0.0)
        # Tier-weighted credibility: authoritative sources count more
        total_weight = sum(
            TIER_CREDIBILITY_WEIGHTS.get(a.source_tier, 1.0) for a in normalized_articles
        ) or 1.0
        credibility = sum(
            a.credibility_score * TIER_CREDIBILITY_WEIGHTS.get(a.source_tier, 1.0)
            for a in normalized_articles
        ) / total_weight
        worthiness = sum(article.worthiness_score for article in normalized_articles) / max(article_count, 1)

        # Velocity: articles added to this cluster in the last 3 hours (rate signal)
        recent_count = await self.repo.count_recent_cluster_articles(cluster.id, within_hours=3)
        velocity = min(recent_count / 5.0, 1.0)

        # Cross-source confirmation: unique outlets covering this story
        unique_sources = await self.repo.count_distinct_sources_for_cluster(cluster.id)
        cross_source = min(unique_sources / 5.0, 1.0)

        # Momentum kept for backwards compat (article total volume)
        momentum = min(article_count / 5, 1.0)

        # Step 7 dimensions: audience_fit, novelty, monetization, risk_penalty
        audience_fit = self._heuristic_audience_fit(cluster, normalized_articles)
        novelty = self._heuristic_novelty(cluster, velocity)
        monetization = self._heuristic_monetization(cluster)
        risk_penalty = 0.3 if cluster.risk_level in (RiskLevel.RISKY.value, RiskLevel.UNSAFE.value) else (
            0.1 if cluster.risk_level == RiskLevel.SENSITIVE.value else 0.0
        )

        weights = self._load_score_weights(tenant_settings, brand_profile=brand_profile)
        is_high_risk = self._is_high_risk_topic(cluster, normalized_articles)
        threshold = 0.40
        if is_high_risk:
            threshold = 0.62
        elif cluster.risk_level == RiskLevel.SENSITIVE.value:
            threshold = 0.52
        score = round(
            (freshness    * weights["freshness"])
            + (credibility  * weights["credibility"])
            + (velocity     * weights["velocity"])
            + (cross_source * weights["cross_source"])
            + (worthiness   * weights["worthiness"])
            + (audience_fit * weights["audience_fit"])
            + (novelty      * weights["novelty"])
            + (monetization * weights["monetization"])
            - (risk_penalty * weights.get("risk_penalty_factor", 0.15)),
            4,
        )
        score = max(0.0, min(1.0, score))
        decision = "generate" if score >= threshold else "hold"

        # Trend direction based on velocity vs momentum
        if velocity >= 0.6:
            cluster.trend_direction = "up"
        elif velocity <= 0.1 and momentum >= 0.6:
            cluster.trend_direction = "down"
        else:
            cluster.trend_direction = "flat"

        source_mix = {
            "tier1": sum(1 for a in normalized_articles if a.source_tier == SourceTier.AUTHORITATIVE.value),
            "signal": sum(1 for a in normalized_articles if a.source_tier == SourceTier.SIGNAL.value),
            "amplification": sum(1 for a in normalized_articles if a.source_tier == SourceTier.AMPLIFICATION.value),
        }
        reasons = [
            f"freshness={freshness:.2f}",
            f"credibility={credibility:.2f}",
            f"velocity={velocity:.2f}",
            f"cross_source={cross_source:.2f}",
            f"worthiness={worthiness:.2f}",
            f"audience_fit={audience_fit:.2f}",
            f"novelty={novelty:.2f}",
            f"monetization={monetization:.2f}",
            f"risk_penalty={risk_penalty:.2f}",
            f"threshold={threshold:.2f}",
        ]
        trend = TrendScore(
            tenant_id=cluster.tenant_id,
            story_cluster_id=cluster.id,
            score=score,
            freshness_score=freshness,
            credibility_score=credibility,
            momentum_score=momentum,
            worthiness_score=worthiness,
            velocity_score=velocity,
            cross_source_score=cross_source,
            audience_fit_score=audience_fit,
            novelty_score=novelty,
            monetization_score=monetization,
            risk_penalty_score=risk_penalty,
            calculated_at=datetime.now(timezone.utc),
            explanation={
                "reasons": "; ".join(reasons),
                "source_mix": json.dumps(source_mix),
                "high_risk": str(is_high_risk).lower(),
            },
        )
        content_decision = ContentWorthinessDecision(
            cluster_id=cluster.id,
            decision=decision,
            score=score,
            reasons=reasons,
        )
        return trend, content_decision
