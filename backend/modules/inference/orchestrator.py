"""
Multi-role content generation orchestrator.

Runs the inference pipeline in sequence:
  1. Extractor  — facts, entities, geography, vertical, risk flags
  2. Scorer     — audience_fit, novelty, monetization, risk_penalty, composite
  3. Planner    — format, platforms, hook, structure, CTA
  4. Writer     — per-platform drafts
  5. Reviewer   — quality/compliance check with optional revision
  6. Optimizer  — A/B variants + engagement prediction

Each stage's output feeds into the next. The full trace is returned for
explainability.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.modules.inference.roles import (
    run_extractor,
    run_optimizer,
    run_planner,
    run_reviewer,
    run_scorer,
    run_writer,
)
from backend.modules.inference.schemas import (
    ExtractorOutput,
    OptimizerOutput,
    PlannerOutput,
    ReviewerOutput,
    ScorerOutput,
    WriterOutput,
)
from backend.modules.inference.providers import LLMProvider, get_llm_provider


@dataclass
class OrchestrationResult:
    extractor: ExtractorOutput
    scorer: ScorerOutput
    planner: PlannerOutput
    writer: WriterOutput
    reviewer: ReviewerOutput
    optimizer: OptimizerOutput
    # The final recommended draft (post-review + post-optimize)
    final_draft: str = ""
    # Whether the pipeline recommended publishing
    recommended: bool = False


class ContentOrchestrator:
    """
    Stateless orchestrator — instantiate per request.

    Usage::
        orchestrator = ContentOrchestrator()
        result = await orchestrator.run(context)
    """

    def __init__(self, llm: LLMProvider | None = None):
        self.llm = llm or get_llm_provider()

    async def run(
        self,
        *,
        # Cluster / brief context
        headline: str,
        summary: str,
        body: str = "",
        angle: str = "",
        talking_points: list[str] | None = None,
        content_vertical: str = "general",
        risk_level: str = "safe",
        # Brand context
        tone: str = "authoritative",
        audience: str = "General social audience",
        preferred_platforms: list[str] | None = None,
        hashtags_strategy: str = "balanced",
        cta: str = "",
        # Score threshold — below this, pipeline returns recommended=False
        worthiness_threshold: float = 0.35,
    ) -> OrchestrationResult:
        talking_points = talking_points or []
        preferred_platforms = preferred_platforms or ["x", "bluesky"]

        # ── Stage 0: Hard block on unsafe content ────────────────────────────
        if risk_level == "unsafe":
            return OrchestrationResult(
                extractor=ExtractorOutput(),
                scorer=ScorerOutput(
                    audience_fit=0.0, novelty=0.0, monetization=0.0,
                    risk_penalty=1.0, composite=0.0,
                    reasoning="Blocked: unsafe risk level",
                ),
                planner=PlannerOutput(),
                writer=WriterOutput(),
                reviewer=ReviewerOutput(passed=False, issues=["Content blocked: risk_level=unsafe"]),
                optimizer=OptimizerOutput(),
                final_draft="",
                recommended=False,
            )

        # ── Stage 1: Extract ─────────────────────────────────────────────────
        extractor_out = await run_extractor(self.llm, f"{headline}\n{summary}\n{body}"[:3000])

        # ── Stage 2: Score ───────────────────────────────────────────────────
        scorer_out = await run_scorer(
            self.llm,
            headline=headline,
            summary=summary,
            vertical=content_vertical,
            risk_level=risk_level,
        )

        if scorer_out.composite < worthiness_threshold:
            # Short-circuit: not worth generating content
            return OrchestrationResult(
                extractor=extractor_out,
                scorer=scorer_out,
                planner=PlannerOutput(),
                writer=WriterOutput(),
                reviewer=ReviewerOutput(passed=False, issues=["Score below threshold"]),
                optimizer=OptimizerOutput(),
                final_draft="",
                recommended=False,
            )

        # ── Stage 3: Plan ────────────────────────────────────────────────────
        planner_out = await run_planner(
            self.llm,
            headline=headline,
            angle=angle or summary[:200],
            tone=tone,
            audience=audience,
            preferred_platforms=preferred_platforms,
        )

        # ── Stage 4: Write ───────────────────────────────────────────────────
        effective_platforms = planner_out.target_platforms or preferred_platforms
        writer_out = await run_writer(
            self.llm,
            headline=headline,
            hook=planner_out.hook or headline,
            talking_points=talking_points or planner_out.structure,
            tone=tone,
            cta=cta or planner_out.cta,
            hashtags_strategy=hashtags_strategy,
            platforms=effective_platforms,
        )

        # Use the first available draft for review/optimize
        first_platform = effective_platforms[0] if effective_platforms else "x"
        primary_draft = writer_out.drafts.get(first_platform, headline)

        # ── Stage 5: Review ──────────────────────────────────────────────────
        reviewer_out = await run_reviewer(
            self.llm,
            draft=primary_draft,
            risk_level=risk_level,
        )

        # Apply revision if reviewer suggests one
        if not reviewer_out.passed and reviewer_out.revised_draft:
            primary_draft = reviewer_out.revised_draft
            writer_out.drafts[first_platform] = primary_draft

        # ── Stage 6: Optimize ────────────────────────────────────────────────
        optimizer_out = await run_optimizer(
            self.llm,
            draft=primary_draft,
            platform=first_platform,
        )

        # Final draft = recommended variant from optimizer
        idx = optimizer_out.recommended_variant_index
        final_draft = (
            optimizer_out.variants[idx]
            if optimizer_out.variants and idx < len(optimizer_out.variants)
            else primary_draft
        )

        return OrchestrationResult(
            extractor=extractor_out,
            scorer=scorer_out,
            planner=planner_out,
            writer=writer_out,
            reviewer=reviewer_out,
            optimizer=optimizer_out,
            final_draft=final_draft,
            recommended=reviewer_out.passed,
        )
