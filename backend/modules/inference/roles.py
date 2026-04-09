"""
Multi-role LLM inference pipeline.

Each role is a pure async function that takes a context dict and returns
a typed Pydantic model. Roles are stateless and composable — the orchestrator
wires them together in sequence.

Providers:
  - Uses the shared inference provider abstraction
  - Falls back to rule-based defaults if JSON parsing fails (graceful degradation)
"""
from __future__ import annotations

import json
import re
from typing import Any

from backend.modules.inference.schemas import (
    ExtractorOutput,
    OptimizerOutput,
    PlannerOutput,
    ReviewerOutput,
    ScorerOutput,
    WriterOutput,
)
from backend.modules.inference.providers import LLMProvider


def _parse_json_output(raw: str, default: dict) -> dict:
    """Strip markdown fences and parse JSON; return default on failure."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        # Try to extract first JSON object via regex
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except (json.JSONDecodeError, ValueError):
                pass
    return default


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

_EXTRACTOR_PROMPT = """\
Extract structured facts from the following article text.
Respond ONLY with valid JSON matching this schema:
{{
  "claims": ["claim1", "claim2"],
  "entities": ["Entity1", "Entity2"],
  "geography": {{"country": "US"}},
  "content_vertical": "tech",
  "risk_flags": [],
  "language": "en"
}}

Article:
{text}
"""


async def run_extractor(llm: LLMProvider, text: str) -> ExtractorOutput:
    prompt = _EXTRACTOR_PROMPT.format(text=text[:4000])
    data = await llm.generate_structured_json(
        prompt,
        schema_hint=ExtractorOutput().model_dump(),
        max_tokens=400,
        temperature=0.1,
        task="extractor",
    )
    try:
        return ExtractorOutput.model_validate(data)
    except Exception:
        return ExtractorOutput()


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

_SCORER_PROMPT = """\
Score this story for content worthiness. Respond ONLY with valid JSON:
{{
  "audience_fit": 0.0-1.0,
  "novelty": 0.0-1.0,
  "monetization": 0.0-1.0,
  "risk_penalty": 0.0-1.0,
  "composite": 0.0-1.0,
  "reasoning": "brief explanation"
}}

Composite = (audience_fit * 0.35) + (novelty * 0.30) + (monetization * 0.20) - (risk_penalty * 0.15)
Clamp composite to [0, 1].

Story headline: {headline}
Summary: {summary}
Content vertical: {vertical}
Risk level: {risk_level}
"""


async def run_scorer(
    llm: LLMProvider,
    *,
    headline: str,
    summary: str,
    vertical: str,
    risk_level: str,
) -> ScorerOutput:
    prompt = _SCORER_PROMPT.format(
        headline=headline[:200],
        summary=summary[:500],
        vertical=vertical,
        risk_level=risk_level,
    )
    data = await llm.generate_structured_json(
        prompt,
        schema_hint={
            "audience_fit": 0.5,
            "novelty": 0.5,
            "monetization": 0.5,
            "risk_penalty": 0.0,
            "composite": 0.5,
            "reasoning": "",
        },
        max_tokens=300,
        temperature=0.1,
        task="scorer",
    )
    try:
        output = ScorerOutput.model_validate(data)
    except Exception:
        output = ScorerOutput(
            audience_fit=0.5,
            novelty=0.5,
            monetization=0.5,
            risk_penalty=0.0,
            composite=0.5,
        )
    # Recompute composite if LLM didn't follow formula
    computed = (
        (output.audience_fit * 0.35)
        + (output.novelty * 0.30)
        + (output.monetization * 0.20)
        - (output.risk_penalty * 0.15)
    )
    output.composite = round(max(0.0, min(1.0, computed)), 4)
    return output


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

_PLANNER_PROMPT = """\
Create a content plan for the following story. Respond ONLY with valid JSON:
{{
  "recommended_format": "text",
  "target_platforms": ["x", "bluesky"],
  "hook": "Opening hook sentence",
  "structure": ["Section 1", "Section 2", "Conclusion"],
  "cta": "Follow for more updates",
  "estimated_word_count": 200
}}

Story headline: {headline}
Angle: {angle}
Tone: {tone}
Target audience: {audience}
Brand preferred platforms: {platforms}
"""


async def run_planner(
    llm: LLMProvider,
    *,
    headline: str,
    angle: str,
    tone: str,
    audience: str,
    preferred_platforms: list[str],
) -> PlannerOutput:
    prompt = _PLANNER_PROMPT.format(
        headline=headline[:200],
        angle=angle[:300],
        tone=tone,
        audience=audience[:200],
        platforms=", ".join(preferred_platforms),
    )
    data = await llm.generate_structured_json(
        prompt,
        schema_hint=PlannerOutput(target_platforms=preferred_platforms[:3]).model_dump(),
        max_tokens=400,
        temperature=0.3,
        task="planner",
    )
    try:
        result = PlannerOutput.model_validate(data)
        if not result.target_platforms:
            result.target_platforms = preferred_platforms[:3]
        return result
    except Exception:
        return PlannerOutput(
            recommended_format="text",
            target_platforms=preferred_platforms[:3],
            hook=headline,
        )


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

_WRITER_PROMPT = """\
Write social media content for the following platforms.
Respond ONLY with valid JSON where keys are platform names and values are draft text:
{{
  "x": "Tweet text (max 280 chars)",
  "bluesky": "Bluesky post (max 300 chars)",
  "instagram": "Instagram caption"
}}

Headline: {headline}
Hook: {hook}
Key points: {points}
Tone: {tone}
CTA: {cta}
Hashtags: {hashtags_strategy}
Platforms: {platforms}
"""


async def run_writer(
    llm: LLMProvider,
    *,
    headline: str,
    hook: str,
    talking_points: list[str],
    tone: str,
    cta: str,
    hashtags_strategy: str,
    platforms: list[str],
) -> WriterOutput:
    prompt = _WRITER_PROMPT.format(
        headline=headline[:200],
        hook=hook[:200],
        points="; ".join(talking_points[:5]),
        tone=tone,
        cta=cta[:150],
        hashtags_strategy=hashtags_strategy,
        platforms=", ".join(platforms),
    )
    data = await llm.generate_structured_json(
        prompt,
        schema_hint={platform: headline for platform in platforms},
        max_tokens=600,
        temperature=0.7,
        task="writer",
    )
    # Extract hashtags from any platform's text
    all_text = " ".join(str(v) for v in data.values())
    hashtags = re.findall(r"#\w+", all_text)
    try:
        drafts = {k: str(v) for k, v in data.items() if k in platforms}
        return WriterOutput(drafts=drafts, hashtags=list(set(hashtags)))
    except Exception:
        return WriterOutput(drafts={p: headline for p in platforms})


# ---------------------------------------------------------------------------
# Reviewer
# ---------------------------------------------------------------------------

_REVIEWER_PROMPT = """\
Review the following social media draft for quality and compliance.
Respond ONLY with valid JSON:
{{
  "passed": true/false,
  "issues": ["issue1", "issue2"],
  "revised_draft": "Revised text or null",
  "confidence": 0.0-1.0
}}

Draft: {draft}
Guidelines:
- No misinformation or unverified claims
- Brand-safe language
- Within platform character limits
- Clear and engaging
Risk level: {risk_level}
"""


async def run_reviewer(
    llm: LLMProvider,
    *,
    draft: str,
    risk_level: str,
) -> ReviewerOutput:
    prompt = _REVIEWER_PROMPT.format(
        draft=draft[:600],
        risk_level=risk_level,
    )
    data = await llm.generate_structured_json(
        prompt,
        schema_hint={"passed": True, "issues": [], "revised_draft": None, "confidence": 0.5},
        max_tokens=300,
        temperature=0.1,
        task="reviewer",
    )
    try:
        return ReviewerOutput.model_validate(data)
    except Exception:
        return ReviewerOutput(passed=True)


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------

_OPTIMIZER_PROMPT = """\
Generate 2-3 A/B variants of this social media draft optimised for engagement.
Respond ONLY with valid JSON:
{{
  "variants": ["Variant A text", "Variant B text"],
  "predicted_engagement": {{"0": 0.72, "1": 0.65}},
  "recommended_variant_index": 0
}}

Original draft: {draft}
Platform: {platform}
"""


async def run_optimizer(
    llm: LLMProvider,
    *,
    draft: str,
    platform: str,
) -> OptimizerOutput:
    prompt = _OPTIMIZER_PROMPT.format(draft=draft[:500], platform=platform)
    data = await llm.generate_structured_json(
        prompt,
        schema_hint=OptimizerOutput(variants=[draft], predicted_engagement={"0": 0.5}).model_dump(),
        max_tokens=400,
        temperature=0.6,
        task="optimizer",
    )
    try:
        output = OptimizerOutput.model_validate(data)
    except Exception:
        output = OptimizerOutput(
            variants=[draft],
            predicted_engagement={"0": 0.5},
            recommended_variant_index=0,
        )
    return output
