"""Trend candidate sync, listing, operator actions, and expiry."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import UUID

from backend.modules.source_ingestion.enums import SourceTier
from backend.modules.story_intelligence.models import (
    NormalizedArticle,
    RiskLevel,
    StoryCluster,
    TrendCandidate,
    TrendCandidateStatus,
    TrendScore,
    TrendWorkflowState,
)
from backend.modules.story_intelligence.schemas import TrendCandidateResponse


class TrendCandidateMixin:
    """Candidate persistence and editorial workflow operations."""

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
            "amplification": sum(
                1 for article in normalized_articles if article.source_tier == SourceTier.AMPLIFICATION.value
            ),
        }
        score_explanation = {
            "trend_score": trend_score.explanation,
            "cluster_explainability": cluster.explainability,
            "blocked": blocked,
            "risk_level": cluster.risk_level,
            "source_mix_breakdown": tier_breakdown,
            "contradiction_detected": self.scorer._has_contradiction(normalized_articles),
            "review_risk_label": topic_review["label"],
            "review_reasons": topic_review["reasons"],
            "topic_categories": topic_review["topic_categories"],
        }
        if candidate:
            candidate.date_bucket = datetime.now(timezone.utc).date()
            candidate.primary_topic = cluster.primary_topic
            candidate.subtopics = (
                cluster.explainability.get("keywords", "").split(", ")
                if cluster.explainability.get("keywords")
                else []
            )
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
                subtopics=(
                    cluster.explainability.get("keywords", "").split(", ")
                    if cluster.explainability.get("keywords")
                    else []
                ),
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

    async def get_trend_candidate_detail(
        self, tenant_id: UUID, candidate_id: UUID
    ) -> TrendCandidateResponse | None:
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
