from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.content_generation.models import GeneratedAssetGroupStatus, GeneratedAssetType
from backend.modules.content_generation.service import ContentGenerationService
from backend.modules.editorial_briefs.models import BriefStatus
from backend.modules.inference.orchestrator import OrchestrationResult
from backend.modules.inference.schemas import (
    ExtractorOutput,
    OptimizerOutput,
    PlannerOutput,
    ReviewerOutput,
    ScorerOutput,
    WriterOutput,
)


@pytest.mark.asyncio
async def test_generate_persists_stage_and_platform_package_assets() -> None:
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

    tenant_id = uuid.uuid4()
    plan = MagicMock()
    plan.id = uuid.uuid4()
    plan.story_cluster_id = uuid.uuid4()
    plan.brand_profile_id = None
    plan.decision = "generate"
    plan.content_format = "text"
    plan.tone = "authoritative"
    plan.target_platforms = ["x", "threads", "bluesky", "instagram", "tiktok", "youtube_shorts"]
    plan.hashtags_strategy = "balanced"
    plan.recommended_cta = "Follow for updates"
    svc.plan_repo.get_content_plan = AsyncMock(return_value=plan)
    svc.plan_repo.get_brand_profile = AsyncMock(return_value=None)

    cluster = MagicMock()
    cluster.id = plan.story_cluster_id
    cluster.headline = "AI platform launches workflow automation"
    cluster.summary = "A new tool promises faster publishing for editorial teams."
    cluster.primary_topic = "ai"
    cluster.content_vertical = "tech"
    cluster.risk_level = "safe"
    cluster.explainability = {"keywords": "ai, workflow, automation"}
    cluster.workflow_state = "asset_generation"
    svc.story_repo.get_cluster = AsyncMock(return_value=cluster)

    article = MagicMock()
    article.source_name = "Trusted Wire"
    article.title = "AI workflow platform launches"
    article.summary = "The launch targets editorial teams."
    article.body = "The launch targets editorial teams with automation."
    article.canonical_url = "https://example.com/story"
    article.published_at = None
    svc.story_repo.list_normalized_for_cluster = AsyncMock(return_value=[article])

    brief = MagicMock()
    brief.id = uuid.uuid4()
    brief.status = BriefStatus.APPROVED.value
    brief.angle = "Operational speed for publishers"
    brief.talking_points = ["Automation", "Editorial ops", "Faster approvals"]
    brief.evidence_links = ["https://example.com/story"]
    brief.tone_guidance = "authoritative"
    brief.cta_strategy = "Follow for updates"

    job = MagicMock()
    job.id = uuid.uuid4()
    job.grounding_bundle = {"headline": cluster.headline, "summary": cluster.summary, "topic": cluster.primary_topic}
    asset_group = MagicMock()
    asset_group.id = uuid.uuid4()
    asset_group.generation_trace = {}
    asset_group.quality_report = {}
    asset_group.asset_types = []
    asset_group.status = GeneratedAssetGroupStatus.CREATED.value
    svc.repo.create_job = AsyncMock(return_value=job)
    svc.repo.create_asset_group = AsyncMock(return_value=asset_group)

    orch_result = OrchestrationResult(
        extractor=ExtractorOutput(
            claims=["The platform launched for editorial teams"],
            entities=["Editorial teams", "AI platform"],
            content_vertical="tech",
            risk_flags=[],
        ),
        scorer=ScorerOutput(
            audience_fit=0.8,
            novelty=0.7,
            monetization=0.6,
            risk_penalty=0.1,
            composite=0.72,
            reasoning="Strong fit",
        ),
        planner=PlannerOutput(
            recommended_format="both",
            target_platforms=plan.target_platforms,
            hook="This AI launch matters for content operators",
            structure=["Hook", "Why it matters", "What changes next"],
            cta="Follow for updates",
            estimated_word_count=180,
        ),
        writer=WriterOutput(
            drafts={
                "x": "AI workflow automation is getting much more operational.",
                "threads": "There is a real shift happening in editorial automation.",
                "bluesky": "Editorial automation is moving faster.",
                "instagram": "Editorial workflows are getting a serious automation upgrade.",
                "tiktok": "Here is why this editorial automation launch matters.",
                "youtube_shorts": "This launch shows where content ops is heading next.",
            },
            hashtags=["#AI", "#ContentOps", "#Editorial"],
        ),
        reviewer=ReviewerOutput(passed=True, issues=[], revised_draft=None, confidence=0.92),
        optimizer=OptimizerOutput(
            variants=[
                "AI workflow automation is getting much more operational.",
                "A new AI ops platform just changed editorial workflows.",
                "Content ops is becoming a competitive advantage.",
            ],
            predicted_engagement={"0": 0.74, "1": 0.69, "2": 0.66},
            recommended_variant_index=0,
        ),
        final_draft="AI workflow automation is getting much more operational.",
        recommended=True,
    )

    captured_assets: list[dict[str, object]] = []

    async def capture_asset(**kwargs):
        captured_assets.append(kwargs)
        return MagicMock()

    svc._create_asset = AsyncMock(side_effect=capture_asset)

    with (
        patch("backend.modules.content_generation.service.EditorialBriefRepository") as mock_brief_repo,
        patch("backend.modules.content_generation.service.ContentOrchestrator") as mock_orchestrator_cls,
        patch("backend.modules.analytics.optimization.OptimizationService.best_tone_for_platform", new=AsyncMock(return_value=None)),
        patch("backend.modules.content_generation.image_service.ImageGenerationService.generate_for_job", new=AsyncMock(return_value=None)),
        patch("backend.modules.content_generation.tts_service.TTSService.generate_for_job", new=AsyncMock(return_value=None)),
    ):
        mock_brief_repo.return_value.get_by_cluster = AsyncMock(return_value=brief)
        mock_orchestrator = MagicMock()
        mock_orchestrator.run = AsyncMock(return_value=orch_result)
        mock_orchestrator_cls.return_value = mock_orchestrator

        await svc.generate(tenant_id=tenant_id, plan_id=plan.id)

    generated_types = {call["asset_type"].value for call in captured_assets}
    assert GeneratedAssetType.PLANNER_STAGE.value in generated_types
    assert GeneratedAssetType.WRITER_STAGE.value in generated_types
    assert GeneratedAssetType.REVIEWER_STAGE.value in generated_types
    assert GeneratedAssetType.FORMATTER_STAGE.value in generated_types
    assert GeneratedAssetType.RENDERER_INPUT.value in generated_types
    assert GeneratedAssetType.THREAD.value in generated_types
    assert GeneratedAssetType.HASHTAG_PACK.value in generated_types
    assert GeneratedAssetType.CAROUSEL_SLIDES.value in generated_types
    assert GeneratedAssetType.SHOT_LIST.value in generated_types
    assert GeneratedAssetType.TITLE_VARIANTS.value in generated_types
    assert GeneratedAssetType.DESCRIPTION.value in generated_types
    assert GeneratedAssetType.TAGS.value in generated_types
    assert GeneratedAssetType.BEAT_SHEET.value in generated_types
    assert GeneratedAssetType.FACT_CHECKLIST.value in generated_types
    assert GeneratedAssetType.ATTRIBUTION_LIST.value in generated_types
    assert GeneratedAssetType.POLICY_FLAGS.value in generated_types
    assert GeneratedAssetType.BRAND_VOICE_REPORT.value in generated_types
    assert GeneratedAssetType.ORIGINALITY_REPORT.value in generated_types
    assert asset_group.status == GeneratedAssetGroupStatus.REVIEWED.value
    assert asset_group.quality_report["risk_label"] == "low"
    assert cluster.workflow_state == "asset_review"


@pytest.mark.asyncio
async def test_regenerate_asset_group_uses_instruction_path() -> None:
    svc = object.__new__(ContentGenerationService)
    svc.repo = AsyncMock()
    svc.generate = AsyncMock()

    tenant_id = uuid.uuid4()
    asset_group_id = uuid.uuid4()
    content_plan_id = uuid.uuid4()
    content_job_id = uuid.uuid4()

    asset_group = MagicMock()
    asset_group.id = asset_group_id
    asset_group.content_job_id = content_job_id
    asset_group.status = GeneratedAssetGroupStatus.REVIEWED.value
    asset_group.generation_trace = {}

    job = MagicMock()
    job.id = content_job_id
    job.content_plan_id = content_plan_id

    new_job = MagicMock()

    svc.repo.get_asset_group = AsyncMock(return_value=asset_group)
    svc.repo.get_job = AsyncMock(return_value=job)
    svc.repo.create_revision = AsyncMock()
    svc.generate = AsyncMock(return_value=new_job)

    result = await svc.regenerate_asset_group(
        tenant_id=tenant_id,
        asset_group_id=asset_group_id,
        instruction="Trim the CTA and make the hooks safer",
        requested_by_user_id=uuid.uuid4(),
        source_channel="dashboard_asset_group",
    )

    assert result is new_job
    assert asset_group.status == GeneratedAssetGroupStatus.REGENERATED.value
    assert asset_group.generation_trace["regeneration_instruction"] == "Trim the CTA and make the hooks safer"
    svc.repo.create_revision.assert_awaited_once()
    svc.generate.assert_awaited_once()
