from __future__ import annotations

import re
from typing import Any


FAIL_CLOSED_CATEGORIES = {"politics", "conflicts", "elections", "markets", "health"}
NEGATION_TOKENS = {"not", "no", "never", "denied", "deny", "false", "without"}
HARMFUL_FRAMING_PATTERNS = {
    "fear": ("panic", "terrified", "disaster", "catastrophe", "meltdown"),
    "manipulation": ("guaranteed", "secret trick", "you must", "everyone must", "only idiots"),
    "abuse": ("traitor", "vermin", "subhuman", "wipe them out"),
}
PLATFORM_POLICY_PATTERNS = {
    "x": ("guaranteed return", "insider tip", "election stolen", "miracle cure"),
    "bluesky": ("guaranteed return", "miracle cure"),
    "threads": ("guaranteed return", "miracle cure"),
    "instagram": ("before it gets banned", "miracle cure", "guaranteed return"),
    "tiktok": ("before it gets banned", "miracle cure", "guaranteed return"),
    "youtube": ("miracle cure", "guaranteed return", "election stolen"),
    "youtube_shorts": ("miracle cure", "guaranteed return", "election stolen"),
}
TOPIC_KEYWORDS = {
    "politics": {"politic", "government", "minister", "president", "congress", "parliament", "campaign"},
    "conflicts": {"war", "conflict", "military", "missile", "strike", "battle", "invasion"},
    "elections": {"election", "vote", "ballot", "polling", "voter", "referendum"},
    "markets": {"market", "stocks", "shares", "crypto", "trading", "nasdaq", "dow", "s&p"},
    "health": {"health", "medical", "disease", "vaccine", "drug", "treatment", "patient", "hospital"},
}


class FactRiskReviewService:
    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()

    def _tokenize(self, text: str) -> list[str]:
        return [token for token in self._normalize_text(text).split() if token]

    def _sentence_split(self, text: str) -> list[str]:
        chunks = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]
        return chunks or ([text.strip()] if text.strip() else [])

    def _contains_negation(self, text: str) -> bool:
        tokens = set(self._tokenize(text))
        return bool(tokens & NEGATION_TOKENS)

    def _core_overlap(self, left: str, right: str) -> set[str]:
        ignored = NEGATION_TOKENS | {"the", "and", "for", "with", "that", "this", "from", "into", "about"}
        left_tokens = {token for token in self._tokenize(left) if len(token) > 2 and token not in ignored}
        right_tokens = {token for token in self._tokenize(right) if len(token) > 2 and token not in ignored}
        return left_tokens & right_tokens

    def classify_topic_categories(
        self,
        *,
        content_vertical: str,
        headline: str,
        summary: str,
        claims: list[str],
        keywords: list[str],
    ) -> list[str]:
        haystack = " ".join([headline, summary, *claims, *keywords]).lower()
        detected: set[str] = set()
        if content_vertical in {"politics", "conflicts"}:
            detected.add(content_vertical)
        if content_vertical == "economy":
            detected.add("markets")
        for category, phrases in TOPIC_KEYWORDS.items():
            if any(phrase in haystack for phrase in phrases):
                detected.add(category)
        return sorted(detected)

    def should_fail_closed(self, topic_categories: list[str]) -> bool:
        return any(category in FAIL_CLOSED_CATEGORIES for category in topic_categories)

    def build_fact_checklist(
        self,
        *,
        topic: str,
        topic_risk_level: str,
        claims: list[str],
        source_articles: list[Any],
        evidence_links: list[str],
    ) -> dict[str, object]:
        approved_links = {link for link in evidence_links if link}
        approved_articles = [
            article for article in source_articles if getattr(article, "canonical_url", None) in approved_links
        ] or source_articles
        items: list[dict[str, object]] = []
        factual_points = claims or [topic]
        for claim in factual_points[:8]:
            supporting = []
            normalized_claim = self._normalize_text(claim)
            for article in approved_articles:
                haystack = self._normalize_text(
                    " ".join(
                        [
                            getattr(article, "title", "") or "",
                            getattr(article, "summary", "") or "",
                            getattr(article, "body", "") or "",
                        ]
                    )
                )
                overlap = self._core_overlap(normalized_claim, haystack)
                if overlap:
                    supporting.append(
                        {
                            "title": getattr(article, "title", ""),
                            "url": getattr(article, "canonical_url", None),
                            "matched_terms": sorted(overlap)[:6],
                        }
                    )
            items.append(
                {
                    "claim": claim,
                    "supported": bool(supporting),
                    "supporting_sources": supporting[:3],
                    "checked_against_evidence": sorted(approved_links)[:5],
                }
            )
        return {
            "topic": topic,
            "risk_level": topic_risk_level,
            "checks": items,
        }

    def detect_claim_contradictions(
        self,
        *,
        extracted_claims: list[str],
        generated_texts: dict[str, str],
    ) -> list[dict[str, str]]:
        contradictions: list[dict[str, str]] = []
        for platform, text in generated_texts.items():
            for sentence in self._sentence_split(text):
                for claim in extracted_claims[:8]:
                    overlap = self._core_overlap(sentence, claim)
                    if len(overlap) < 2:
                        continue
                    if self._contains_negation(sentence) != self._contains_negation(claim):
                        contradictions.append(
                            {
                                "platform": platform,
                                "claim": claim,
                                "generated": sentence,
                            }
                        )
        return contradictions

    def detect_harmful_framing(self, generated_texts: dict[str, str]) -> list[dict[str, str]]:
        findings: list[dict[str, str]] = []
        for platform, text in generated_texts.items():
            lowered = text.lower()
            for category, phrases in HARMFUL_FRAMING_PATTERNS.items():
                for phrase in phrases:
                    if phrase in lowered:
                        findings.append({"platform": platform, "category": category, "phrase": phrase})
        return findings

    def review_platform_policies(
        self,
        *,
        generated_texts: dict[str, str],
        topic_categories: list[str],
    ) -> list[dict[str, object]]:
        reviews: list[dict[str, object]] = []
        for platform, text in generated_texts.items():
            lowered = text.lower()
            issues = [pattern for pattern in PLATFORM_POLICY_PATTERNS.get(platform, ()) if pattern in lowered]
            blocked = bool(issues)
            if self.should_fail_closed(topic_categories):
                blocked = True
                if "manual review required for regulated topic" not in issues:
                    issues.append("manual review required for regulated topic")
            reviews.append(
                {
                    "platform": platform,
                    "label": "blocked" if blocked else ("high" if issues else "low"),
                    "blocked": blocked,
                    "issues": issues,
                }
            )
        return reviews

    def review_topic(
        self,
        *,
        content_vertical: str,
        headline: str,
        summary: str,
        claims: list[str],
        keywords: list[str],
    ) -> dict[str, object]:
        categories = self.classify_topic_categories(
            content_vertical=content_vertical,
            headline=headline,
            summary=summary,
            claims=claims,
            keywords=keywords,
        )
        fail_closed = self.should_fail_closed(categories)
        reasons = [f"{category} content requires fail-closed handling" for category in categories if category in FAIL_CLOSED_CATEGORIES]
        label = "high" if fail_closed else ("medium" if categories else "low")
        return {
            "label": label,
            "blocked": False,
            "fail_closed": fail_closed,
            "topic_categories": categories,
            "reasons": reasons,
        }

    def review_generated_package(
        self,
        *,
        content_vertical: str,
        headline: str,
        summary: str,
        topic: str,
        topic_risk_level: str,
        claims: list[str],
        keywords: list[str],
        source_articles: list[Any],
        evidence_links: list[str],
        generated_texts: dict[str, str],
        reviewer_issues: list[str],
    ) -> dict[str, object]:
        topic_review = self.review_topic(
            content_vertical=content_vertical,
            headline=headline,
            summary=summary,
            claims=claims,
            keywords=keywords,
        )
        fact_checklist = self.build_fact_checklist(
            topic=topic,
            topic_risk_level=topic_risk_level,
            claims=claims,
            source_articles=source_articles,
            evidence_links=evidence_links,
        )
        unsupported_claims = [item for item in fact_checklist["checks"] if not item["supported"]]
        contradictions = self.detect_claim_contradictions(
            extracted_claims=claims,
            generated_texts=generated_texts,
        )
        harmful_framing = self.detect_harmful_framing(generated_texts)
        platform_policy = self.review_platform_policies(
            generated_texts=generated_texts,
            topic_categories=list(topic_review["topic_categories"]),
        )

        warnings = list(reviewer_issues)
        warnings.extend(f"{len(unsupported_claims)} unsupported claims detected" for _ in [0] if unsupported_claims)
        warnings.extend("Generated copy contradicts extracted claims" for _ in [0] if contradictions)
        warnings.extend("Harmful framing markers detected" for _ in [0] if harmful_framing)
        warnings.extend(
            f"{review['platform']} platform policy review flagged content"
            for review in platform_policy
            if review["issues"]
        )
        warnings.extend(topic_review["reasons"])

        blocked = bool(
            topic_review["fail_closed"]
            or contradictions
            or harmful_framing
            or any(review["blocked"] for review in platform_policy)
        )
        if blocked:
            label = "blocked"
        elif unsupported_claims or any(review["issues"] for review in platform_policy):
            label = "high"
        elif warnings:
            label = "medium"
        else:
            label = "low"

        policy_flags = {
            "label": label,
            "blocked": blocked,
            "warnings": warnings,
            "risk_level": topic_risk_level,
            "topic_categories": topic_review["topic_categories"],
            "fail_closed": topic_review["fail_closed"],
            "unsupported_claims": len(unsupported_claims),
            "contradictions": contradictions,
            "harmful_framing": harmful_framing,
            "platform_policy": platform_policy,
        }
        return {
            "fact_checklist": fact_checklist,
            "policy_flags": policy_flags,
            "risk_label": label,
            "blocked": blocked,
            "topic_categories": topic_review["topic_categories"],
        }
