"""Individual multi-role LLM runners."""
from __future__ import annotations


from backend.modules.inference.providers import LLMProvider
from backend.modules.inference.schemas import (
    ExtractorOutput,
    PlannerOutput,
    ScorerOutput,
)

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
