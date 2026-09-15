from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import UUID

from langdetect import detect  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession

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
    TrendScore,
)
from backend.modules.story_intelligence.providers import get_llm_provider
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository
from backend.modules.story_intelligence.schemas import ContentWorthinessDecision


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "from",
    "this",
    "have",
    "will",
    "into",
    "after",
    "about",
    "latest",
}


class ClusterScorer:
    """Keyword/risk heuristics and cluster worthiness scoring."""

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

    def _fact_review_service(self) -> FactRiskReviewService:
        if self._fact_review is None:
            self._fact_review = FactRiskReviewService()
        return self._fact_review

    def _extract_keywords(self, text: str, limit: int = 8) -> list[str]:
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower())
        counts = Counter(token for token in tokens if token not in STOPWORDS)
        return [word for word, _ in counts.most_common(limit)]

    def _infer_language(self, text: str) -> str:
        try:
            return cast(str, detect(text))
        except Exception:
            return "en"

    def _freshness_score(self, published_at: datetime | None) -> float:
        if not published_at:
            return 0.35
        age_hours = max((datetime.now(timezone.utc) - published_at).total_seconds() / 3600, 0)
        if age_hours <= 6:
            return 1.0
        if age_hours <= 24:
            return 0.8
        if age_hours <= 72:
            return 0.55
        return 0.25

    def _risk_level(self, keywords: list[str]) -> RiskLevel:
        risky_terms = {"war", "attack", "death", "lawsuit", "crisis", "ban"}
        unsafe_terms = {"graphic", "extremist"}
        sensitive_terms = {"election", "vote", "market", "stocks", "health", "disease"}
        if any(term in unsafe_terms for term in keywords):
            return RiskLevel.UNSAFE
        if any(term in risky_terms for term in keywords):
            return RiskLevel.RISKY
        if any(term in sensitive_terms for term in keywords):
            return RiskLevel.SENSITIVE
        return RiskLevel.SAFE

    def _extract_claims(self, body: str, title: str) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", f"{title}. {body}")
        claims: list[str] = []
        for sentence in sentences:
            cleaned = sentence.strip()
            if len(cleaned) < 30:
                continue
            if any(char.isdigit() for char in cleaned) or any(
                token in cleaned.lower()
                for token in ("said", "announced", "confirmed", "reported", "will", "has", "have")
            ):
                claims.append(cleaned[:280])
            if len(claims) >= 5:
                break
        return claims

    def _has_contradiction(self, normalized_articles: list[NormalizedArticle]) -> bool:
        claims = [claim for article in normalized_articles for claim in article.claims[:3]]
        generated_texts = {f"article_{index}": claim for index, claim in enumerate(claims)}
        return bool(
            self._fact_review_service().detect_claim_contradictions(
                extracted_claims=claims,
                generated_texts=generated_texts,
            )
        )

    def _is_high_risk_topic(self, cluster: StoryCluster, normalized_articles: list[NormalizedArticle]) -> bool:
        vertical = cluster.content_vertical or ContentVertical.GENERAL.value
        keywords = [keyword for article in normalized_articles for keyword in article.keywords]
        categories = self._fact_review_service().classify_topic_categories(
            content_vertical=vertical,
            headline=cluster.headline,
            summary=cluster.summary,
            claims=[claim for article in normalized_articles for claim in article.claims[:3]],
            keywords=keywords,
        )
        cluster.explainability["review_risk_label"] = "high" if self._fact_review_service().should_fail_closed(categories) else "low"
        cluster.explainability["review_reasons"] = ", ".join(categories)
        return (
            vertical in {v.value for v in HIGH_RISK_VERTICALS}
            or self._fact_review_service().should_fail_closed(categories)
        )

    def _check_risk_gate(
        self, cluster: StoryCluster, normalized_articles: list[NormalizedArticle]
    ) -> tuple[bool, str | None]:
        """
        Returns (blocked, block_reason).
        blocked=True means worthy_for_content must remain False.
        """
        risk = cluster.risk_level
        if risk == RiskLevel.UNSAFE.value:
            cluster.block_reason = ClusterBlockReason.UNSAFE_CONTENT.value
            cluster.awaiting_confirmation = False
            return True, ClusterBlockReason.UNSAFE_CONTENT.value

        is_high_risk_vertical = self._is_high_risk_topic(cluster, normalized_articles)

        if risk == RiskLevel.RISKY.value or is_high_risk_vertical:
            # Count unique Tier 1 (authoritative) sources
            tier1_count = len(
                {
                    a.source_name
                    for a in normalized_articles
                    if a.source_tier == SourceTier.AUTHORITATIVE.value
                }
            )
            cluster.tier1_sources_confirmed = tier1_count
            if tier1_count < 2:
                cluster.block_reason = ClusterBlockReason.INSUFFICIENT_TIER1_CONFIRMATION.value
                cluster.awaiting_confirmation = True
                return True, ClusterBlockReason.INSUFFICIENT_TIER1_CONFIRMATION.value
            if self._has_contradiction(normalized_articles):
                cluster.block_reason = ClusterBlockReason.CONTRADICTORY_CLAIMS.value
                cluster.awaiting_confirmation = False
                return True, ClusterBlockReason.CONTRADICTORY_CLAIMS.value
            # Enough Tier 1 confirmation — clear block
            cluster.awaiting_confirmation = False
            cluster.block_reason = None

        return False, None

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

    def _heuristic_audience_fit(self, cluster: StoryCluster, articles: list[NormalizedArticle]) -> float:
        """
        Lightweight heuristic: authoritative + signal tier articles in high-engagement verticals
        correlate with audience fit. Higher cross-source coverage also boosts fit.
        """
        auth_count = sum(1 for a in articles if a.source_tier == SourceTier.AUTHORITATIVE.value)
        fit = min(auth_count / max(len(articles), 1), 1.0)
        if cluster.content_vertical in {v.value for v in HIGH_RISK_VERTICALS}:
            fit = min(fit + 0.1, 1.0)  # high-risk verticals have higher audience interest
        return round(fit, 4)

    def _heuristic_novelty(self, cluster: StoryCluster, velocity: float) -> float:
        """
        Novelty correlates with velocity (fast-rising) and low article_count
        (not yet a saturated story).
        """
        saturation_penalty = min(cluster.article_count / 20, 1.0)
        novelty = velocity * (1.0 - saturation_penalty * 0.5)
        return round(min(novelty, 1.0), 4)

    def _heuristic_monetization(self, cluster: StoryCluster) -> float:
        """
        High-value verticals (gaming, fashion, beauty) have higher monetization potential.
        General = medium, high-risk verticals = lower (brand-unsafe).
        """
        vertical_scores = {
            "gaming": 0.85, "fashion": 0.80, "beauty": 0.80,
            "tech": 0.75, "entertainment": 0.70, "general": 0.50,
            "economy": 0.40, "politics": 0.25, "conflicts": 0.20,
        }
        return vertical_scores.get(cluster.content_vertical, 0.50)

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

