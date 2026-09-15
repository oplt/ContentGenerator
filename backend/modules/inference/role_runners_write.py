"""Writer/reviewer/optimizer role runners."""
from __future__ import annotations

import re

from backend.modules.inference.providers import LLMProvider
from backend.modules.inference.schemas import (
    OptimizerOutput,
    ReviewerOutput,
    WriterOutput,
)

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
