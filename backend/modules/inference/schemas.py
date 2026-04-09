"""
Structured output schemas for the multi-role inference pipeline.

Each role produces a typed dataclass / Pydantic model so callers get
strongly-typed results rather than raw strings.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Extractor role output
# ---------------------------------------------------------------------------

class ExtractorOutput(BaseModel):
    """Structured facts extracted from raw article/cluster content."""
    claims: list[str] = Field(default_factory=list, description="Key factual claims")
    entities: list[str] = Field(default_factory=list, description="Named entities (people, orgs, places)")
    geography: dict[str, str] = Field(default_factory=dict, description="country/region codes")
    content_vertical: str = Field(default="general", description="Detected content vertical")
    risk_flags: list[str] = Field(default_factory=list, description="Detected risk flags")
    language: str = Field(default="en")


# ---------------------------------------------------------------------------
# Scorer role output
# ---------------------------------------------------------------------------

class ScorerOutput(BaseModel):
    """Audience fit + novelty + monetization scores for a cluster."""
    audience_fit: float = Field(ge=0.0, le=1.0, description="How well this story fits the target audience")
    novelty: float = Field(ge=0.0, le=1.0, description="How novel/fresh this angle is")
    monetization: float = Field(ge=0.0, le=1.0, description="Commercial appeal")
    risk_penalty: float = Field(ge=0.0, le=1.0, description="Risk adjustment (higher = more penalised)")
    composite: float = Field(ge=0.0, le=1.0, description="Weighted composite score")
    reasoning: str = Field(default="")


# ---------------------------------------------------------------------------
# Planner role output
# ---------------------------------------------------------------------------

class PlannerOutput(BaseModel):
    """Content plan: format, platforms, hook, structure."""
    recommended_format: str = Field(default="text", description="text | video | both")
    target_platforms: list[str] = Field(default_factory=list)
    hook: str = Field(default="", description="Opening hook sentence")
    structure: list[str] = Field(default_factory=list, description="Ordered content sections")
    cta: str = Field(default="", description="Call to action")
    estimated_word_count: int = Field(default=200)


# ---------------------------------------------------------------------------
# Writer role output
# ---------------------------------------------------------------------------

class WriterOutput(BaseModel):
    """Generated content drafts per platform."""
    drafts: dict[str, str] = Field(
        default_factory=dict,
        description="platform → draft text mapping",
    )
    hashtags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Reviewer role output
# ---------------------------------------------------------------------------

class ReviewerOutput(BaseModel):
    """Quality and compliance review of a draft."""
    passed: bool
    issues: list[str] = Field(default_factory=list)
    revised_draft: str | None = Field(default=None, description="Revised text if issues found")
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


# ---------------------------------------------------------------------------
# Optimizer role output
# ---------------------------------------------------------------------------

class OptimizerOutput(BaseModel):
    """A/B variant and engagement prediction."""
    variants: list[str] = Field(default_factory=list, description="Text variants to A/B test")
    predicted_engagement: dict[str, float] = Field(
        default_factory=dict, description="variant_index → predicted engagement score"
    )
    recommended_variant_index: int = Field(default=0)
