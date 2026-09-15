from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from backend.modules.content_generation.generation_context import normalize_text, sentence_split
from backend.modules.story_intelligence.models import NormalizedArticle


def _max_pairwise_ratio(left: list[str], right: list[str]) -> float:
    best = 0.0
    for a in left:
        na = normalize_text(a)
        for b in right:
            best = max(best, SequenceMatcher(None, na, normalize_text(b)).ratio())
    return best


def _max_internal_ratio(texts: list[str]) -> float:
    best = 0.0
    for index, text in enumerate(texts):
        nt = normalize_text(text)
        for other in texts[index + 1 :]:
            best = max(best, SequenceMatcher(None, nt, normalize_text(other)).ratio())
    return best


def _repeated_phrases(texts: list[str]) -> list[dict[str, object]]:
    phrase_counts: dict[str, int] = {}
    for text in texts:
        for sentence in sentence_split(text):
            normalized = normalize_text(sentence)
            if len(normalized.split()) < 4:
                continue
            phrase_counts[normalized] = phrase_counts.get(normalized, 0) + 1
    return [
        {"phrase": phrase[:120], "count": count}
        for phrase, count in phrase_counts.items()
        if count > 2
    ][:10]


def _candidate_texts(asset_manifest: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for asset in asset_manifest:
        text = str(asset.get("content", "")).strip()
        if text:
            out.append(text)
    return out


def _source_snippets(source_articles: list[NormalizedArticle]) -> list[str]:
    out: list[str] = []
    for article in source_articles[:5]:
        snippet = ((article.summary or article.body or article.title or "")[:500]).strip()
        if snippet:
            out.append(snippet)
    return out


def _similarity_label(score: float) -> str:
    if score >= 0.93:
        return "blocked"
    if score >= 0.85:
        return "high"
    return "low"


def measure_originality(
    *,
    asset_manifest: list[dict[str, Any]],
    source_articles: list[NormalizedArticle],
) -> dict[str, object]:
    candidates = _candidate_texts(asset_manifest)
    max_source = _max_pairwise_ratio(candidates[:12], _source_snippets(source_articles))
    label = _similarity_label(max_source)
    return {
        "blocked": label == "blocked",
        "label": label,
        "max_source_similarity": round(max_source, 4),
        "max_internal_similarity": round(_max_internal_ratio(candidates), 4),
        "repeated_phrases": _repeated_phrases(candidates),
    }


class OriginalityMixin:
    def _measure_originality(
        self,
        *,
        asset_manifest: list[dict[str, Any]],
        source_articles: list[NormalizedArticle],
    ) -> dict[str, object]:
        return measure_originality(
            asset_manifest=asset_manifest,
            source_articles=source_articles,
        )
