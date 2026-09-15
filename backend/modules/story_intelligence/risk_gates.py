"""Risk-gate checks that can block content-worthy cluster decisions."""

from __future__ import annotations

from backend.modules.fact_review.service import FactRiskReviewService
from backend.modules.source_ingestion.enums import ContentVertical, HIGH_RISK_VERTICALS, SourceTier
from backend.modules.story_intelligence.models import (
    ClusterBlockReason,
    NormalizedArticle,
    RiskLevel,
    StoryCluster,
)


class RiskGateMixin:
    """Contradiction / tier-confirmation gates used by ClusterScorer."""

    _fact_review: FactRiskReviewService | None

    def _fact_review_service(self) -> FactRiskReviewService:
        if self._fact_review is None:
            self._fact_review = FactRiskReviewService()
        return self._fact_review

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
        cluster.explainability["review_risk_label"] = (
            "high" if self._fact_review_service().should_fail_closed(categories) else "low"
        )
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
