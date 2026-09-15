from __future__ import annotations

from typing import Any, cast

from backend.modules.fact_review.service import FactRiskReviewService
from backend.modules.story_intelligence.models import NormalizedArticle, StoryCluster


def hallucination_guard(text: str, entities: list[str]) -> bool:
    """Return True if at least half of the key entities appear in the generated text."""
    if not entities:
        return True
    text_lower = text.lower()
    matches = sum(1 for e in entities if e.lower() in text_lower)
    return matches >= max(1, len(entities) // 2)


class QualityMixin:
    fact_review: FactRiskReviewService | None

    def _fact_review_service(self) -> FactRiskReviewService:
        if not hasattr(self, "fact_review") or self.fact_review is None:
            self.fact_review = FactRiskReviewService()
        return self.fact_review

    def _hallucination_guard(self, text: str, entities: list[str]) -> bool:
        return hallucination_guard(text, entities)

    def _build_fact_checklist(
        self,
        *,
        cluster: StoryCluster,
        source_articles: list[NormalizedArticle],
        claims: list[str],
        evidence_links: list[str] | None = None,
    ) -> dict[str, object]:
        return self._fact_review_service().build_fact_checklist(
            topic=cluster.primary_topic,
            topic_risk_level=getattr(cluster, "risk_level", "safe") or "safe",
            claims=claims or [cluster.summary or cluster.headline],
            source_articles=source_articles,
            evidence_links=evidence_links or [],
        )

    def _build_attribution_list(
        self,
        *,
        brief: Any,
        source_articles: list[NormalizedArticle],
    ) -> dict[str, object]:
        links = []
        for article in source_articles[:8]:
            links.append(
                {
                    "source": article.source_name,
                    "title": article.title,
                    "url": article.canonical_url,
                    "published_at": article.published_at.isoformat() if article.published_at else None,
                }
            )
        for url in getattr(brief, "evidence_links", []) or []:
            if not any(link["url"] == url for link in links):
                links.append(
                    {"source": "brief_evidence", "title": url, "url": url, "published_at": None}
                )
        return {"count": len(links), "links": links}

    def _build_policy_flags(
        self,
        *,
        cluster: StoryCluster,
        brief: Any,
        orch_result: Any,
        fact_checklist: dict[str, object],
        source_articles: list[NormalizedArticle],
        effective_platforms: list[str],
    ) -> dict[str, object]:
        generated_texts = {
            platform: str(orch_result.writer.drafts.get(platform) or "").strip()
            for platform in effective_platforms
            if str(orch_result.writer.drafts.get(platform) or "").strip()
        }
        review = self._fact_review_service().review_generated_package(
            content_vertical=getattr(cluster, "content_vertical", "general") or "general",
            headline=cluster.headline,
            summary=cluster.summary or "",
            topic=cluster.primary_topic,
            topic_risk_level=getattr(cluster, "risk_level", "safe") or "safe",
            claims=list(orch_result.extractor.claims or []),
            keywords=[
                part.strip()
                for part in cluster.explainability.get("keywords", "").split(",")
                if part.strip()
            ],
            source_articles=source_articles,
            evidence_links=list(getattr(brief, "evidence_links", []) or []),
            generated_texts=generated_texts,
            reviewer_issues=list(orch_result.reviewer.issues or []),
        )
        policy_flags = cast(dict[str, object], review.get("policy_flags", {}))
        policy_flags["fact_checklist_topic"] = fact_checklist.get("topic")
        return policy_flags
