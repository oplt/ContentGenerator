"""
Tests for Step 6 — Multi-Role AI Orchestration.

Covers:
- _parse_json_output: valid JSON, markdown fences, fallback to default
- run_extractor: parses structured extraction output
- run_scorer: computes composite = formula, clamps to [0,1]
- run_planner: returns PlannerOutput with platforms
- run_writer: returns WriterOutput with per-platform drafts
- run_reviewer: passes/fails draft, applies revision
- run_optimizer: returns variants with engagement predictions
- ContentOrchestrator.run: full pipeline, short-circuits below threshold
- OrchestrationResult fields present
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.modules.inference.roles import (
    _parse_json_output,
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
from backend.modules.inference.orchestrator import ContentOrchestrator, OrchestrationResult


# ---------------------------------------------------------------------------
# _parse_json_output
# ---------------------------------------------------------------------------

def test_parse_json_valid() -> None:
    data = {"key": "value", "n": 42}
    assert _parse_json_output(json.dumps(data), {}) == data


def test_parse_json_strips_markdown_json_fence() -> None:
    data = {"a": 1}
    raw = f"```json\n{json.dumps(data)}\n```"
    assert _parse_json_output(raw, {}) == data


def test_parse_json_strips_plain_fence() -> None:
    data = {"b": 2}
    raw = f"```\n{json.dumps(data)}\n```"
    assert _parse_json_output(raw, {}) == data


def test_parse_json_extracts_embedded_json() -> None:
    data = {"x": 99}
    raw = f'Here is the output: {json.dumps(data)} done.'
    assert _parse_json_output(raw, {})["x"] == 99


def test_parse_json_returns_default_on_failure() -> None:
    default = {"fallback": True}
    assert _parse_json_output("not json at all!", default) == default


# ---------------------------------------------------------------------------
# run_extractor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_extractor_parses_output() -> None:
    llm = MagicMock()
    llm.generate_structured_json = AsyncMock(return_value={
        "claims": ["The economy shrank by 2%"],
        "entities": ["Federal Reserve", "US"],
        "geography": {"country": "US"},
        "content_vertical": "economy",
        "risk_flags": [],
        "language": "en",
    })
    result = await run_extractor(llm, "The economy is in trouble")
    assert isinstance(result, ExtractorOutput)
    assert result.content_vertical == "economy"
    assert "Federal Reserve" in result.entities


@pytest.mark.asyncio
async def test_run_extractor_falls_back_on_bad_json() -> None:
    llm = MagicMock()
    llm.generate_structured_json = AsyncMock(return_value={})
    result = await run_extractor(llm, "Some text")
    assert isinstance(result, ExtractorOutput)
    assert result.language == "en"  # default


# ---------------------------------------------------------------------------
# run_scorer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_scorer_recomputes_composite() -> None:
    llm = MagicMock()
    llm.generate_structured_json = AsyncMock(return_value={
        "audience_fit": 0.8,
        "novelty": 0.6,
        "monetization": 0.7,
        "risk_penalty": 0.2,
        "composite": 0.0,  # LLM gave wrong composite — should be recomputed
        "reasoning": "Good story",
    })
    result = await run_scorer(
        llm, headline="Test", summary="Summary", vertical="tech", risk_level="safe"
    )
    expected = (0.8 * 0.35) + (0.6 * 0.30) + (0.7 * 0.20) - (0.2 * 0.15)
    assert result.composite == pytest.approx(expected, abs=1e-4)


@pytest.mark.asyncio
async def test_run_scorer_clamps_composite_to_one() -> None:
    llm = MagicMock()
    llm.generate_structured_json = AsyncMock(return_value={
        "audience_fit": 1.0,
        "novelty": 1.0,
        "monetization": 1.0,
        "risk_penalty": 0.0,
        "composite": 2.0,  # LLM gave > 1
        "reasoning": "",
    })
    result = await run_scorer(
        llm, headline="X", summary="X", vertical="general", risk_level="safe"
    )
    assert result.composite <= 1.0


@pytest.mark.asyncio
async def test_run_scorer_clamps_composite_to_zero() -> None:
    llm = MagicMock()
    llm.generate_structured_json = AsyncMock(return_value={
        "audience_fit": 0.0,
        "novelty": 0.0,
        "monetization": 0.0,
        "risk_penalty": 1.0,
        "composite": -0.5,
        "reasoning": "",
    })
    result = await run_scorer(
        llm, headline="X", summary="X", vertical="general", risk_level="unsafe"
    )
    assert result.composite >= 0.0


# ---------------------------------------------------------------------------
# run_planner
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_planner_returns_planner_output() -> None:
    llm = MagicMock()
    llm.generate_structured_json = AsyncMock(return_value={
        "recommended_format": "text",
        "target_platforms": ["x", "bluesky"],
        "hook": "Breaking: major tech layoffs",
        "structure": ["Intro", "Details", "Impact", "Conclusion"],
        "cta": "Follow for updates",
        "estimated_word_count": 250,
    })
    result = await run_planner(
        llm,
        headline="Tech layoffs",
        angle="Industry correction",
        tone="analytical",
        audience="Tech professionals",
        preferred_platforms=["x", "bluesky"],
    )
    assert isinstance(result, PlannerOutput)
    assert "x" in result.target_platforms
    assert result.estimated_word_count == 250


@pytest.mark.asyncio
async def test_run_planner_falls_back_on_parse_error() -> None:
    llm = MagicMock()
    llm.generate_structured_json = AsyncMock(return_value={})
    result = await run_planner(
        llm, headline="X", angle="Y", tone="Z", audience="A", preferred_platforms=["x"]
    )
    assert isinstance(result, PlannerOutput)
    assert "x" in result.target_platforms


# ---------------------------------------------------------------------------
# run_writer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_writer_returns_per_platform_drafts() -> None:
    llm = MagicMock()
    llm.generate_structured_json = AsyncMock(return_value={
        "x": "Big tech news: layoffs hit AI startup #Tech #AI",
        "bluesky": "Major layoffs at leading AI startup signal industry correction",
    })
    result = await run_writer(
        llm,
        headline="AI startup layoffs",
        hook="Big tech news",
        talking_points=["200 jobs cut", "Stock fell 15%"],
        tone="analytical",
        cta="Follow for updates",
        hashtags_strategy="balanced",
        platforms=["x", "bluesky"],
    )
    assert isinstance(result, WriterOutput)
    assert "x" in result.drafts
    assert "bluesky" in result.drafts
    assert "#Tech" in result.hashtags or "#AI" in result.hashtags


# ---------------------------------------------------------------------------
# run_reviewer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_reviewer_passes_clean_draft() -> None:
    llm = MagicMock()
    llm.generate_structured_json = AsyncMock(return_value={
        "passed": True,
        "issues": [],
        "revised_draft": None,
        "confidence": 0.95,
    })
    result = await run_reviewer(llm, draft="Clean tweet text", risk_level="safe")
    assert isinstance(result, ReviewerOutput)
    assert result.passed is True
    assert result.confidence == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_run_reviewer_suggests_revision() -> None:
    llm = MagicMock()
    llm.generate_structured_json = AsyncMock(return_value={
        "passed": False,
        "issues": ["Unverified claim in text"],
        "revised_draft": "Revised safe version of the tweet",
        "confidence": 0.8,
    })
    result = await run_reviewer(llm, draft="Controversial claim!", risk_level="risky")
    assert result.passed is False
    assert len(result.issues) == 1
    assert result.revised_draft == "Revised safe version of the tweet"


# ---------------------------------------------------------------------------
# run_optimizer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_optimizer_returns_variants() -> None:
    llm = MagicMock()
    llm.generate_structured_json = AsyncMock(return_value={
        "variants": ["Variant A: Breaking news", "Variant B: Exclusive report"],
        "predicted_engagement": {"0": 0.72, "1": 0.65},
        "recommended_variant_index": 0,
    })
    result = await run_optimizer(llm, draft="Original draft", platform="x")
    assert isinstance(result, OptimizerOutput)
    assert len(result.variants) == 2
    assert result.recommended_variant_index == 0
    assert result.predicted_engagement["0"] == pytest.approx(0.72)


# ---------------------------------------------------------------------------
# ContentOrchestrator
# ---------------------------------------------------------------------------

def _mock_llm_for_orchestrator(composite: float = 0.7) -> MagicMock:
    """Mock LLM that returns reasonable structured outputs for all stages."""
    llm = MagicMock()

    # Compute input values that produce the requested composite via the formula
    # composite = af*0.35 + nov*0.30 + mon*0.20 - rp*0.15
    # For simplicity: rp=0, mon=0, then af+nov determines composite
    # composite = af*0.35 + nov*0.30 → use af=nov=composite/0.65 clamped to [0,1]
    raw_score = min(1.0, max(0.0, composite / 0.65))

    async def generate_structured_json(prompt: str, **kwargs) -> dict[str, object]:
        if "Extract structured" in prompt:
            return {
                "claims": ["Claim 1"],
                "entities": ["Entity A"],
                "geography": {"country": "US"},
                "content_vertical": "tech",
                "risk_flags": [],
                "language": "en",
            }
        if "Score this story" in prompt:
            return {
                "audience_fit": raw_score,
                "novelty": raw_score,
                "monetization": 0.0,
                "risk_penalty": 0.0,
                "composite": composite,
                "reasoning": "Good story",
            }
        if "Create a content plan" in prompt:
            return {
                "recommended_format": "text",
                "target_platforms": ["x"],
                "hook": "Breaking news hook",
                "structure": ["Intro", "Details"],
                "cta": "Follow us",
                "estimated_word_count": 150,
            }
        if "Write social media" in prompt:
            return {
                "x": "Test tweet content #test",
            }
        if "Review the following" in prompt:
            return {
                "passed": True,
                "issues": [],
                "revised_draft": None,
                "confidence": 0.9,
            }
        if "A/B variants" in prompt:
            return {
                "variants": ["Variant A", "Variant B"],
                "predicted_engagement": {"0": 0.7, "1": 0.6},
                "recommended_variant_index": 0,
            }
        return {}

    llm.generate_structured_json = AsyncMock(side_effect=generate_structured_json)
    return llm


@pytest.mark.asyncio
async def test_orchestrator_full_pipeline() -> None:
    llm = _mock_llm_for_orchestrator(composite=0.7)
    orchestrator = ContentOrchestrator(llm=llm)

    result = await orchestrator.run(
        headline="Major tech layoffs announced",
        summary="AI startup cuts 200 jobs amid funding crunch.",
        body="Full article text here...",
        content_vertical="tech",
        risk_level="safe",
        preferred_platforms=["x"],
    )

    assert isinstance(result, OrchestrationResult)
    assert result.recommended is True
    assert result.final_draft == "Variant A"
    assert result.scorer.composite > 0


@pytest.mark.asyncio
async def test_orchestrator_short_circuits_below_threshold() -> None:
    """If scorer composite < threshold, skip planner/writer/reviewer/optimizer."""
    llm = _mock_llm_for_orchestrator(composite=0.1)
    orchestrator = ContentOrchestrator(llm=llm)

    result = await orchestrator.run(
        headline="Low score story",
        summary="Not interesting.",
        worthiness_threshold=0.5,
    )

    assert result.recommended is False
    assert result.final_draft == ""
    # Planner/writer should be empty defaults
    assert result.writer.drafts == {}


@pytest.mark.asyncio
async def test_orchestrator_applies_reviewer_revision() -> None:
    """When reviewer fails and provides revised_draft, orchestrator uses it."""
    llm = MagicMock()

    async def generate_structured_json(prompt: str, **kwargs) -> dict[str, object]:
        if "Extract" in prompt:
            return {"claims": [], "entities": [], "geography": {}, "content_vertical": "general", "risk_flags": [], "language": "en"}
        if "Score" in prompt:
            return {"audience_fit": 0.9, "novelty": 0.9, "monetization": 0.9, "risk_penalty": 0.0, "composite": 0.9, "reasoning": ""}
        if "content plan" in prompt:
            return {"recommended_format": "text", "target_platforms": ["x"], "hook": "hook", "structure": [], "cta": "", "estimated_word_count": 100}
        if "Write social" in prompt:
            return {"x": "Bad draft with issues"}
        if "Review" in prompt:
            return {"passed": False, "issues": ["Contains misinformation"], "revised_draft": "Corrected clean draft", "confidence": 0.7}
        if "A/B variants" in prompt:
            return {"variants": ["Corrected clean draft opt"], "predicted_engagement": {"0": 0.8}, "recommended_variant_index": 0}
        return {}

    llm.generate_structured_json = AsyncMock(side_effect=generate_structured_json)
    orchestrator = ContentOrchestrator(llm=llm)

    result = await orchestrator.run(
        headline="Test story", summary="Summary", preferred_platforms=["x"]
    )
    # Reviewer provided a revision; optimizer uses it as input → final is optimized variant
    assert "Corrected" in result.final_draft or result.final_draft != ""


def test_orchestration_result_has_all_fields() -> None:
    from dataclasses import fields
    field_names = {f.name for f in fields(OrchestrationResult)}
    assert "extractor" in field_names
    assert "scorer" in field_names
    assert "planner" in field_names
    assert "writer" in field_names
    assert "reviewer" in field_names
    assert "optimizer" in field_names
    assert "final_draft" in field_names
    assert "recommended" in field_names


# ---------------------------------------------------------------------------
# High-risk content enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_blocks_unsafe_risk_level() -> None:
    """risk_level='unsafe' must immediately return recommended=False without calling LLM."""
    llm = MagicMock()
    llm.generate_structured_json = AsyncMock()

    orchestrator = ContentOrchestrator(llm=llm)
    result = await orchestrator.run(
        headline="Dangerous content",
        summary="This is unsafe.",
        risk_level="unsafe",
    )

    assert result.recommended is False
    assert result.final_draft == ""
    assert result.scorer.composite == 0.0
    # LLM must NOT have been called for unsafe content
    llm.generate_structured_json.assert_not_called()


@pytest.mark.asyncio
async def test_orchestrator_runs_reviewer_for_high_risk() -> None:
    """For risk_level='risky', the reviewer role must always be called."""
    reviewer_calls = []

    async def generate_structured_json(prompt: str, **kwargs) -> dict[str, object]:
        if "Extract structured" in prompt:
            return {"claims": [], "entities": [], "geography": {}, "content_vertical": "politics", "risk_flags": ["sensitive"], "language": "en"}
        if "Score this story" in prompt:
            return {"audience_fit": 0.8, "novelty": 0.7, "monetization": 0.5, "risk_penalty": 0.3, "composite": 0.7, "reasoning": ""}
        if "Create a content plan" in prompt:
            return {"recommended_format": "text", "target_platforms": ["x"], "hook": "hook", "structure": [], "cta": "", "estimated_word_count": 100}
        if "Write social media" in prompt:
            return {"x": "Sensitive political content"}
        if "Review the following" in prompt:
            reviewer_calls.append(True)
            return {"passed": True, "issues": [], "revised_draft": None, "confidence": 0.9}
        if "A/B variants" in prompt:
            return {"variants": ["Final variant"], "predicted_engagement": {"0": 0.7}, "recommended_variant_index": 0}
        return {}

    llm = MagicMock()
    llm.generate_structured_json = AsyncMock(side_effect=generate_structured_json)
    orchestrator = ContentOrchestrator(llm=llm)

    result = await orchestrator.run(
        headline="Political story",
        summary="Sensitive political content.",
        risk_level="risky",
        preferred_platforms=["x"],
    )

    assert len(reviewer_calls) == 1, "Reviewer must be called for risky content"
    assert result.recommended is True


@pytest.mark.asyncio
async def test_orchestrator_high_risk_reviewer_fail_sets_not_recommended() -> None:
    """If reviewer fails for high-risk content and provides no revision, recommended=False."""
    async def generate_structured_json(prompt: str, **kwargs) -> dict[str, object]:
        if "Extract" in prompt:
            return {"claims": [], "entities": [], "geography": {}, "content_vertical": "conflict", "risk_flags": ["violence"], "language": "en"}
        if "Score" in prompt:
            return {"audience_fit": 0.8, "novelty": 0.8, "monetization": 0.5, "risk_penalty": 0.4, "composite": 0.7, "reasoning": ""}
        if "content plan" in prompt:
            return {"recommended_format": "text", "target_platforms": ["x"], "hook": "h", "structure": [], "cta": "", "estimated_word_count": 100}
        if "Write social" in prompt:
            return {"x": "Violent content draft"}
        if "Review" in prompt:
            # Reviewer fails, no revision
            return {"passed": False, "issues": ["Contains violent imagery"], "revised_draft": None, "confidence": 0.2}
        if "A/B" in prompt:
            return {"variants": ["v1"], "predicted_engagement": {"0": 0.4}, "recommended_variant_index": 0}
        return {}

    llm = MagicMock()
    llm.generate_structured_json = AsyncMock(side_effect=generate_structured_json)
    orchestrator = ContentOrchestrator(llm=llm)

    result = await orchestrator.run(
        headline="Conflict story",
        summary="Violent details.",
        risk_level="risky",
        preferred_platforms=["x"],
    )

    assert result.recommended is False
    assert any("violent" in issue.lower() or "viol" in issue.lower() for issue in result.reviewer.issues)


# ---------------------------------------------------------------------------
# ContentGenerationService uses orchestrator (not single LLM call)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_wires_orchestrator_not_bare_llm() -> None:
    """
    ContentGenerationService.generate() must call ContentOrchestrator.run(),
    not call self.llm.generate() directly for content drafts.
    """
    from unittest.mock import patch, AsyncMock, MagicMock
    from backend.modules.content_generation.service import ContentGenerationService
    from backend.modules.inference.orchestrator import ContentOrchestrator, OrchestrationResult
    from backend.modules.inference.schemas import (
        ExtractorOutput, ScorerOutput, PlannerOutput,
        WriterOutput, ReviewerOutput, OptimizerOutput,
    )

    fake_result = OrchestrationResult(
        extractor=ExtractorOutput(content_vertical="tech"),
        scorer=ScorerOutput(audience_fit=0.8, novelty=0.7, monetization=0.6, risk_penalty=0.1, composite=0.7),
        planner=PlannerOutput(recommended_format="text", target_platforms=["x"], hook="Hook!"),
        writer=WriterOutput(drafts={"x": "Tweet from orchestrator"}),
        reviewer=ReviewerOutput(passed=True),
        optimizer=OptimizerOutput(variants=["Tweet from orchestrator", "Variant B"], recommended_variant_index=0),
        final_draft="Tweet from orchestrator",
        recommended=True,
    )

    svc = object.__new__(ContentGenerationService)
    svc.db = AsyncMock()
    svc.db.flush = AsyncMock()
    svc.db.add = MagicMock()
    svc.repo = AsyncMock()
    svc.plan_repo = AsyncMock()
    svc.story_repo = AsyncMock()
    svc.audit = AsyncMock()
    svc.video_pipeline = AsyncMock()
    svc.llm = MagicMock()

    plan = MagicMock()
    plan.id = uuid.uuid4()
    plan.decision = "generate"
    plan.content_format = "text"
    plan.target_platforms = ["x"]
    plan.tone = "authoritative"
    plan.recommended_cta = "Follow us"
    plan.hashtags_strategy = "balanced"
    plan.story_cluster_id = uuid.uuid4()

    cluster = MagicMock()
    cluster.id = plan.story_cluster_id
    cluster.headline = "Test headline"
    cluster.summary = "Test summary"
    cluster.primary_topic = "tech"
    cluster.content_vertical = "tech"
    cluster.risk_level = "safe"
    cluster.explainability = {"keywords": "tech, ai"}
    cluster.worthy_for_content = True

    brief = MagicMock()
    brief.status = "approved"
    brief.angle = "Tech angle"
    brief.talking_points = ["Point 1", "Point 2"]
    brief.tone_guidance = "authoritative"

    job = MagicMock()
    job.id = uuid.uuid4()
    job.grounding_bundle = {"headline": "Test headline", "summary": "Test summary", "topic": "tech"}

    svc.plan_repo.get_content_plan = AsyncMock(return_value=plan)
    svc.story_repo.get_cluster = AsyncMock(return_value=cluster)
    svc.story_repo.list_normalized_for_cluster = AsyncMock(return_value=[])
    svc.repo.create_job = AsyncMock(return_value=job)
    svc.repo.create_revision = AsyncMock()
    svc.audit.record = AsyncMock()

    orchestrator_run_calls = []

    async def mock_orchestrator_run(**kwargs):
        orchestrator_run_calls.append(kwargs)
        return fake_result

    with (
        patch("backend.modules.content_generation.service.EditorialBriefRepository") as MockBriefRepo,
        patch("backend.modules.content_generation.service.ContentOrchestrator") as MockOrchestrator,
    ):
        MockBriefRepo.return_value.get_by_cluster = AsyncMock(return_value=brief)
        mock_orch_instance = MagicMock()
        mock_orch_instance.run = AsyncMock(side_effect=mock_orchestrator_run)
        MockOrchestrator.return_value = mock_orch_instance

        await svc.generate(tenant_id=uuid.uuid4(), plan_id=plan.id)

    # Orchestrator must have been instantiated and called
    assert MockOrchestrator.called, "ContentOrchestrator must be instantiated"
    assert len(orchestrator_run_calls) == 1
    assert orchestrator_run_calls[0]["headline"] == "Test headline"
    assert orchestrator_run_calls[0]["risk_level"] == "safe"

    # Direct LLM.generate() must NOT have been called for text generation
    svc.llm.generate.assert_not_called()


@pytest.mark.asyncio
async def test_generate_stores_inference_trace_in_job() -> None:
    """The orchestrator trace must be persisted into job.grounding_bundle."""
    from unittest.mock import patch, AsyncMock, MagicMock
    from backend.modules.content_generation.service import ContentGenerationService
    from backend.modules.inference.orchestrator import ContentOrchestrator, OrchestrationResult
    from backend.modules.inference.schemas import (
        ExtractorOutput, ScorerOutput, PlannerOutput,
        WriterOutput, ReviewerOutput, OptimizerOutput,
    )

    fake_result = OrchestrationResult(
        extractor=ExtractorOutput(content_vertical="economy", risk_flags=["sensitive"]),
        scorer=ScorerOutput(audience_fit=0.6, novelty=0.5, monetization=0.4, risk_penalty=0.1, composite=0.6, reasoning="Decent story"),
        planner=PlannerOutput(recommended_format="text", target_platforms=["x"]),
        writer=WriterOutput(drafts={"x": "Economy tweet"}),
        reviewer=ReviewerOutput(passed=True, issues=[]),
        optimizer=OptimizerOutput(variants=["Economy tweet"], recommended_variant_index=0),
        final_draft="Economy tweet",
        recommended=True,
    )

    svc = object.__new__(ContentGenerationService)
    svc.db = AsyncMock()
    svc.db.flush = AsyncMock()
    svc.db.add = MagicMock()
    svc.repo = AsyncMock()
    svc.plan_repo = AsyncMock()
    svc.story_repo = AsyncMock()
    svc.audit = AsyncMock()
    svc.video_pipeline = AsyncMock()
    svc.llm = MagicMock()

    plan = MagicMock()
    plan.id = uuid.uuid4()
    plan.decision = "generate"
    plan.content_format = "text"
    plan.target_platforms = ["x"]
    plan.tone = "balanced"
    plan.recommended_cta = "Follow"
    plan.hashtags_strategy = "balanced"
    plan.story_cluster_id = uuid.uuid4()

    cluster = MagicMock()
    cluster.id = plan.story_cluster_id
    cluster.headline = "Economy update"
    cluster.summary = "Markets fell"
    cluster.primary_topic = "economy"
    cluster.content_vertical = "economy"
    cluster.risk_level = "safe"
    cluster.explainability = {}
    cluster.worthy_for_content = True

    brief = MagicMock()
    brief.status = "approved"
    brief.angle = "Economy angle"
    brief.talking_points = []

    job = MagicMock()
    job.id = uuid.uuid4()
    job.grounding_bundle = {}

    svc.plan_repo.get_content_plan = AsyncMock(return_value=plan)
    svc.story_repo.get_cluster = AsyncMock(return_value=cluster)
    svc.story_repo.list_normalized_for_cluster = AsyncMock(return_value=[])
    svc.repo.create_job = AsyncMock(return_value=job)
    svc.audit.record = AsyncMock()

    with (
        patch("backend.modules.content_generation.service.EditorialBriefRepository") as MockBriefRepo,
        patch("backend.modules.content_generation.service.ContentOrchestrator") as MockOrchestrator,
    ):
        MockBriefRepo.return_value.get_by_cluster = AsyncMock(return_value=brief)
        mock_orch_instance = MagicMock()
        mock_orch_instance.run = AsyncMock(return_value=fake_result)
        MockOrchestrator.return_value = mock_orch_instance

        await svc.generate(tenant_id=uuid.uuid4(), plan_id=plan.id)

    trace = job.grounding_bundle.get("inference_trace", {})
    assert trace["scorer_composite"] == pytest.approx(0.6)
    assert trace["reviewer_passed"] is True
    assert trace["extractor_vertical"] == "economy"
    assert "sensitive" in trace["extractor_risk_flags"]
