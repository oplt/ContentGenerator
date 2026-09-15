"""Normalization helpers for Product Hunter LLM output."""

from __future__ import annotations

import json
from typing import Any

PLACEHOLDER_IDEA_VALUES = {"", "string", "n/a", "unknown", "todo"}


def normalize_repo_assessment(raw_assessment: Any) -> dict[str, Any] | None:
    if not isinstance(raw_assessment, dict):
        return None

    assessment = {
        "what_it_does": stringify_idea_value(raw_assessment.get("what_it_does")),
        "evidence": normalize_text_list(raw_assessment.get("evidence")),
        "strongest_assets": normalize_text_list(raw_assessment.get("strongest_assets")),
        "main_limitations": normalize_text_list(raw_assessment.get("main_limitations")),
        "best_commercial_angle": stringify_idea_value(raw_assessment.get("best_commercial_angle")),
        "confidence": normalize_confidence(raw_assessment.get("confidence")),
    }
    if not any(
        [
            assessment["what_it_does"],
            assessment["evidence"],
            assessment["strongest_assets"],
            assessment["main_limitations"],
            assessment["best_commercial_angle"],
        ]
    ):
        return None
    return assessment


def normalize_generated_ideas(raw_ideas: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_ideas, list):
        return []

    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_ideas, start=1):
        if not isinstance(item, dict):
            continue
        idea = {
            "rank": normalize_rank(item.get("rank"), idx),
            "title": pick_idea_text(item, "title"),
            "positioning": pick_idea_text(item, "positioning", "wow_factor"),
            "target_customer": pick_idea_text(item, "target_customer", "target_audience"),
            "pain_point": pick_idea_text(item, "pain_point", "problem"),
            "product_concept": pick_idea_text(item, "product_concept", "solution"),
            "why_this_repo_fits": pick_idea_text(item, "why_this_repo_fits"),
            "required_extensions": normalize_text_list(item.get("required_extensions")),
            "monetization": normalize_monetization(item.get("monetization")),
            "scores": normalize_scores(item.get("scores")),
            "time_to_mvp": pick_idea_text(item, "time_to_mvp"),
            "key_risks": normalize_text_list(item.get("key_risks")),
            "why_now": pick_idea_text(item, "why_now"),
            "investor_angle": pick_idea_text(item, "investor_angle"),
            "v1_scope": normalize_text_list(item.get("v1_scope")),
            "not_for_v1": normalize_text_list(item.get("not_for_v1")),
        }
        if is_placeholder_idea(idea):
            continue
        normalized.append(idea)
    return normalized


def pick_idea_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        text = stringify_idea_value(value)
        if text:
            return text
    return ""


def stringify_idea_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value).strip()
    if isinstance(value, dict):
        parts = [stringify_idea_value(part) for part in value.values()]
        return "; ".join(part for part in parts if part)
    if isinstance(value, list):
        parts = [stringify_idea_value(part) for part in value]
        return "; ".join(part for part in parts if part)
    return str(value).strip()


def normalize_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := stringify_idea_value(item))]
    text = stringify_idea_value(value)
    return [text] if text else []


def normalize_confidence(value: Any) -> str:
    normalized = stringify_idea_value(value).lower()
    if normalized in {"high", "medium", "low"}:
        return normalized
    return "medium"


def normalize_rank(value: Any, fallback: int) -> int:
    try:
        rank = int(value)
    except (TypeError, ValueError):
        return fallback
    return rank if rank > 0 else fallback


def normalize_monetization(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {
            "model": stringify_idea_value(value.get("model")),
            "pricing_logic": stringify_idea_value(value.get("pricing_logic")),
            "estimated_willingness_to_pay": stringify_idea_value(
                value.get("estimated_willingness_to_pay")
            ),
        }
    text = stringify_idea_value(value)
    return {
        "model": text,
        "pricing_logic": "",
        "estimated_willingness_to_pay": "",
    }


def normalize_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(score, 10))


def normalize_scores(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        value = {}
    return {
        "revenue_potential": normalize_score(value.get("revenue_potential")),
        "customer_urgency": normalize_score(value.get("customer_urgency")),
        "repo_leverage": normalize_score(value.get("repo_leverage")),
        "speed_to_mvp": normalize_score(value.get("speed_to_mvp")),
        "competitive_intensity": normalize_score(value.get("competitive_intensity")),
    }


def format_product_hunter_result_preview(result: Any) -> str:
    if not isinstance(result, dict):
        return f"type={type(result).__name__}"
    ideas_value = result.get("ideas")
    ideas_list = ideas_value if isinstance(ideas_value, list) else []

    payload = {
        "keys": sorted(str(key) for key in result.keys()),
        "repo_assessment_type": type(result.get("repo_assessment")).__name__,
        "ideas_type": type(ideas_value).__name__,
        "ideas_count": len(ideas_list) if ideas_list else None,
        "first_idea_keys": (
            sorted(str(key) for key in result["ideas"][0].keys())
            if ideas_list and isinstance(result["ideas"][0], dict)
            else []
        ),
        "preview": stringify_idea_value(result)[:800],
    }
    return json.dumps(payload, ensure_ascii=True)


def is_placeholder_idea(idea: dict[str, Any]) -> bool:
    values = [
        stringify_idea_value(idea.get("title")).strip().lower(),
        stringify_idea_value(idea.get("positioning")).strip().lower(),
        stringify_idea_value(idea.get("target_customer")).strip().lower(),
        stringify_idea_value(idea.get("pain_point")).strip().lower(),
        stringify_idea_value(idea.get("product_concept")).strip().lower(),
    ]
    non_empty = [value for value in values if value]
    if not non_empty:
        return True
    return all(value in PLACEHOLDER_IDEA_VALUES for value in non_empty)


# Historical private-name aliases.
_normalize_repo_assessment = normalize_repo_assessment
_normalize_generated_ideas = normalize_generated_ideas
_pick_idea_text = pick_idea_text
_stringify_idea_value = stringify_idea_value
_normalize_text_list = normalize_text_list
_normalize_confidence = normalize_confidence
_normalize_rank = normalize_rank
_normalize_monetization = normalize_monetization
_normalize_score = normalize_score
_normalize_scores = normalize_scores
_format_product_hunter_result_preview = format_product_hunter_result_preview
_is_placeholder_idea = is_placeholder_idea
