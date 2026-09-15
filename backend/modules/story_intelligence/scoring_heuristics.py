"""Keyword, freshness, risk, and worthiness heuristics for cluster scoring."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import cast

from langdetect import detect  # type: ignore[import-untyped]

from backend.modules.source_ingestion.enums import HIGH_RISK_VERTICALS, SourceTier
from backend.modules.story_intelligence.models import NormalizedArticle, RiskLevel, StoryCluster


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


class ScoringHeuristicsMixin:
    """Pure/local scoring helpers shared by ClusterScorer."""

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
