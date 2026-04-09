"""
Tests for Step 8 — Analytics + Feedback Loop.

Covers:
- AnalyticsSnapshot.sync_source field presence
- TemplatePerformance model fields and unique constraint metadata
- AnalyticsService.sync_snapshots: real provider path, fallback to synthetic
- AnalyticsService.update_template_performance: incremental mean update
- AnalyticsService._compute_engagement_score: formula
- OptimizationService.recommend: ranking, top_n, low-confidence label
- OptimizationService.best_tone_for_platform / best_vertical_for_platform
- MetricsResult dataclass defaults
- get_metrics_provider factory
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.analytics.models import AnalyticsSnapshot, TemplatePerformance
from backend.modules.analytics.optimization import ContentParameterRecommendation, OptimizationService
from backend.modules.analytics.providers import MetricsResult, get_metrics_provider
from backend.modules.analytics.service import AnalyticsService


# ---------------------------------------------------------------------------
# Model field presence
# ---------------------------------------------------------------------------

def test_analytics_snapshot_has_sync_source() -> None:
    snap = AnalyticsSnapshot()
    assert hasattr(snap, "sync_source")


def test_template_performance_fields() -> None:
    tp = TemplatePerformance()
    for field in (
        "tenant_id", "platform", "tone", "content_vertical",
        "sample_count", "avg_impressions", "avg_likes", "avg_comments",
        "avg_shares", "avg_ctr", "approve_rate", "revise_rate",
        "reject_rate", "engagement_score", "last_computed_at",
    ):
        assert hasattr(tp, field), f"Missing field: {field}"


def test_template_performance_unique_constraint_defined() -> None:
    constraint_names = {c.name for c in TemplatePerformance.__table_args__ if hasattr(c, "name")}
    assert "uq_template_performance_tenant_platform_tone_vertical" in constraint_names


# ---------------------------------------------------------------------------
# MetricsResult defaults
# ---------------------------------------------------------------------------

def test_metrics_result_defaults() -> None:
    m = MetricsResult()
    assert m.impressions == 0
    assert m.sync_source == "synthetic"
    assert m.raw_payload == {}


# ---------------------------------------------------------------------------
# get_metrics_provider factory
# ---------------------------------------------------------------------------

def test_get_metrics_provider_x_with_token() -> None:
    from backend.modules.analytics.providers import XMetricsProvider
    p = get_metrics_provider("x", access_token="tok")
    assert isinstance(p, XMetricsProvider)


def test_get_metrics_provider_instagram_with_token() -> None:
    from backend.modules.analytics.providers import InstagramMetricsProvider
    p = get_metrics_provider("instagram", access_token="tok")
    assert isinstance(p, InstagramMetricsProvider)


def test_get_metrics_provider_youtube_with_api_key() -> None:
    from backend.modules.analytics.providers import YouTubeMetricsProvider
    p = get_metrics_provider("youtube", api_key="key")
    assert isinstance(p, YouTubeMetricsProvider)


def test_get_metrics_provider_no_credentials_returns_none() -> None:
    assert get_metrics_provider("x") is None
    assert get_metrics_provider("instagram") is None
    assert get_metrics_provider("youtube") is None


def test_get_metrics_provider_unknown_platform() -> None:
    assert get_metrics_provider("tiktok", access_token="tok") is None


# ---------------------------------------------------------------------------
# AnalyticsService helpers
# ---------------------------------------------------------------------------

def _make_service() -> AnalyticsService:
    svc = object.__new__(AnalyticsService)
    svc.db = AsyncMock()
    svc.repo = AsyncMock()
    svc.publishing_repo = AsyncMock()
    svc.source_repo = AsyncMock()
    svc.story_repo = AsyncMock()
    return svc


def _make_post(platform: str = "x", platform_post_id: str = "tweet_123") -> MagicMock:
    post = MagicMock()
    post.id = uuid.uuid4()
    post.tenant_id = uuid.uuid4()
    post.platform = platform
    post.post_type = "text"
    post.platform_post_id = platform_post_id
    post.external_post_id = platform_post_id
    post.social_account_id = uuid.uuid4()
    post.raw_payload = {}
    return post


def _make_snapshot(**kwargs) -> AnalyticsSnapshot:
    snap = MagicMock(spec=AnalyticsSnapshot)
    snap.impressions = kwargs.get("impressions", 1200)
    snap.views = kwargs.get("views", 800)
    snap.likes = kwargs.get("likes", 200)
    snap.comments = kwargs.get("comments", 20)
    snap.shares = kwargs.get("shares", 16)
    snap.watch_time_seconds = kwargs.get("watch_time_seconds", 0)
    snap.ctr = kwargs.get("ctr", 0.08)
    snap.sync_source = kwargs.get("sync_source", "synthetic")
    snap.raw_payload = kwargs.get("raw_payload", {})
    snap.platform = kwargs.get("platform", "x")
    snap.snapshot_date = date.today()
    return snap


# ---------------------------------------------------------------------------
# sync_snapshots: provider path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_snapshots_uses_real_provider_when_available() -> None:
    svc = _make_service()
    post = _make_post()

    svc.publishing_repo.list_published_posts = AsyncMock(return_value=[post])
    svc.repo.get_snapshot_for_post = AsyncMock(return_value=None)

    token_mock = MagicMock()
    token_mock.access_token_encrypted = b"enc"
    svc.publishing_repo.get_token_for_account = AsyncMock(return_value=token_mock)

    fake_result = MetricsResult(
        impressions=5000,
        views=4000,
        likes=300,
        comments=50,
        shares=80,
        sync_source="x_api",
        raw_payload={"like_count": 300},
    )

    created_snap = MagicMock(spec=AnalyticsSnapshot)
    svc.repo.create_snapshot = AsyncMock(return_value=created_snap)

    with (
        patch("backend.modules.analytics.service.decrypt_secret", return_value="real_token"),
        patch("backend.modules.analytics.service.get_metrics_provider") as mock_factory,
    ):
        mock_provider = AsyncMock()
        mock_provider.fetch = AsyncMock(return_value=fake_result)
        mock_factory.return_value = mock_provider

        snapshots = await svc.sync_snapshots(post.tenant_id)

    assert len(snapshots) == 1
    # Verify the snapshot was created with real metrics
    call_args = svc.repo.create_snapshot.call_args[0][0]
    assert call_args.impressions == 5000
    assert call_args.sync_source == "x_api"


@pytest.mark.asyncio
async def test_sync_snapshots_falls_back_to_synthetic_on_error() -> None:
    svc = _make_service()
    post = _make_post()

    svc.publishing_repo.list_published_posts = AsyncMock(return_value=[post])
    svc.repo.get_snapshot_for_post = AsyncMock(return_value=None)
    svc.publishing_repo.get_token_for_account = AsyncMock(return_value=None)

    created_snap = MagicMock(spec=AnalyticsSnapshot)
    svc.repo.create_snapshot = AsyncMock(return_value=created_snap)

    with patch("backend.modules.analytics.service.get_metrics_provider", return_value=None):
        snapshots = await svc.sync_snapshots(post.tenant_id)

    assert len(snapshots) == 1
    call_args = svc.repo.create_snapshot.call_args[0][0]
    assert call_args.sync_source == "synthetic"


@pytest.mark.asyncio
async def test_sync_snapshots_updates_existing_snapshot() -> None:
    svc = _make_service()
    post = _make_post()
    existing = _make_snapshot(sync_source="synthetic")

    svc.publishing_repo.list_published_posts = AsyncMock(return_value=[post])
    svc.repo.get_snapshot_for_post = AsyncMock(return_value=existing)
    svc.publishing_repo.get_token_for_account = AsyncMock(return_value=None)

    with patch("backend.modules.analytics.service.get_metrics_provider", return_value=None):
        snapshots = await svc.sync_snapshots(post.tenant_id)

    assert snapshots[0] is existing


@pytest.mark.asyncio
async def test_sync_snapshots_no_platform_post_id_uses_synthetic() -> None:
    svc = _make_service()
    post = _make_post(platform_post_id="")  # no external ID
    post.external_post_id = ""

    svc.publishing_repo.list_published_posts = AsyncMock(return_value=[post])
    svc.repo.get_snapshot_for_post = AsyncMock(return_value=None)

    created_snap = MagicMock(spec=AnalyticsSnapshot)
    svc.repo.create_snapshot = AsyncMock(return_value=created_snap)

    snapshots = await svc.sync_snapshots(post.tenant_id)

    call_args = svc.repo.create_snapshot.call_args[0][0]
    assert call_args.sync_source == "synthetic"


@pytest.mark.asyncio
async def test_sync_snapshots_forced_synthetic_mode() -> None:
    svc = _make_service()
    post = _make_post(platform_post_id="tweet_123")
    svc.publishing_repo.list_published_posts = AsyncMock(return_value=[post])
    svc.repo.get_snapshot_for_post = AsyncMock(return_value=None)
    svc.repo.create_snapshot = AsyncMock(return_value=MagicMock(spec=AnalyticsSnapshot))

    with patch("backend.modules.analytics.service.settings") as mock_settings:
        mock_settings.ANALYTICS_SYNTHETIC_MODE = True
        snapshots = await svc.sync_snapshots(post.tenant_id)

    assert len(snapshots) == 1
    call_args = svc.repo.create_snapshot.call_args[0][0]
    assert call_args.sync_source == "synthetic"


@pytest.mark.asyncio
async def test_overview_includes_dashboard_fields_and_learning_log() -> None:
    svc = _make_service()
    tenant_id = uuid.uuid4()
    snapshot = _make_snapshot(platform="x")
    snapshot.content_format = "video"
    snapshot.topic = "ai"
    snapshot.raw_payload = {
        "hook": "curiosity",
        "publish_hour": "14",
        "brand": "signalforge",
        "follows": 9,
    }
    svc.repo.list_snapshots = AsyncMock(return_value=[snapshot])
    svc.publishing_repo.list_published_posts = AsyncMock(return_value=[MagicMock()])
    source = MagicMock()
    source.name = "BBC"
    source.success_count = 12
    source.failure_count = 1
    svc.source_repo.list_sources = AsyncMock(return_value=[source])
    svc.story_repo.list_clusters = AsyncMock(return_value=[MagicMock(), MagicMock()])

    rec = ContentParameterRecommendation(
        platform="x",
        tone="authoritative",
        content_vertical="general",
        engagement_score=0.42,
        sample_count=4,
        avg_impressions=1000,
        avg_likes=100,
        avg_comments=10,
        avg_shares=5,
        avg_ctr=0.07,
        approve_rate=0.8,
        reject_rate=0.1,
        reasons=["high_ctr"],
    )

    with patch("backend.modules.analytics.optimization.OptimizationService") as mock_opt:
        mock_opt.return_value.recommend = AsyncMock(return_value=[rec])
        overview = await svc.overview(tenant_id)

    assert overview.hook_performance[0].label == "curiosity"
    assert overview.post_time_performance[0].label == "14"
    assert overview.brand_performance[0].label == "signalforge"
    assert overview.topic_to_follower_conversion[0].label == "ai"
    assert overview.platform_comparison[0].label == "x"
    assert overview.learning_log


# ---------------------------------------------------------------------------
# update_template_performance: incremental mean
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_template_performance_creates_new() -> None:
    svc = _make_service()
    tenant_id = uuid.uuid4()
    snap = _make_snapshot(impressions=1000, likes=100, comments=10, shares=20, ctr=0.05)

    svc.repo.get_template_performance = AsyncMock(return_value=None)
    svc.repo.upsert_template_performance = AsyncMock(side_effect=lambda tp: tp)

    tp = await svc.update_template_performance(tenant_id, snap)

    assert tp.sample_count == 1
    assert tp.avg_likes == pytest.approx(100.0)
    assert tp.avg_impressions == pytest.approx(1000.0)


@pytest.mark.asyncio
async def test_update_template_performance_incremental_mean() -> None:
    svc = _make_service()
    tenant_id = uuid.uuid4()

    existing_tp = TemplatePerformance()
    existing_tp.platform = "x"
    existing_tp.tone = "authoritative"
    existing_tp.content_vertical = "general"
    existing_tp.sample_count = 4
    existing_tp.avg_impressions = 2000.0
    existing_tp.avg_likes = 200.0
    existing_tp.avg_comments = 30.0
    existing_tp.avg_shares = 50.0
    existing_tp.avg_ctr = 0.04
    existing_tp.approve_rate = 0.0
    existing_tp.revise_rate = 0.0
    existing_tp.reject_rate = 0.0
    existing_tp.engagement_score = 0.0
    existing_tp.last_computed_at = None

    svc.repo.get_template_performance = AsyncMock(return_value=existing_tp)
    svc.repo.upsert_template_performance = AsyncMock(side_effect=lambda tp: tp)

    snap = _make_snapshot(impressions=3000, likes=400, comments=60, shares=100, ctr=0.08)
    tp = await svc.update_template_performance(tenant_id, snap)

    # n=4 → new_avg = (old * 4 + new) / 5
    assert tp.sample_count == 5
    assert tp.avg_likes == pytest.approx((200 * 4 + 400) / 5)
    assert tp.avg_impressions == pytest.approx((2000 * 4 + 3000) / 5)
    assert tp.last_computed_at is not None


# ---------------------------------------------------------------------------
# _compute_engagement_score
# ---------------------------------------------------------------------------

def test_compute_engagement_score_zero_samples() -> None:
    tp = TemplatePerformance()
    tp.sample_count = 0
    tp.avg_likes = 0
    tp.avg_shares = 0
    tp.avg_comments = 0
    tp.avg_ctr = 0
    assert AnalyticsService._compute_engagement_score(tp) == pytest.approx(0.0)


def test_compute_engagement_score_clamped_at_one() -> None:
    tp = TemplatePerformance()
    tp.sample_count = 10
    tp.avg_likes = 100_000  # well above MAX_LIKES
    tp.avg_shares = 100_000
    tp.avg_comments = 100_000
    tp.avg_ctr = 100.0
    score = AnalyticsService._compute_engagement_score(tp)
    assert score == pytest.approx(1.0)


def test_compute_engagement_score_formula() -> None:
    tp = TemplatePerformance()
    tp.sample_count = 5
    tp.avg_likes = 5000    # 5000/10000 = 0.5 → contribution 0.5*0.4=0.2
    tp.avg_shares = 2500   # 2500/5000  = 0.5 → contribution 0.5*0.3=0.15
    tp.avg_comments = 1000 # 1000/2000  = 0.5 → contribution 0.5*0.2=0.1
    tp.avg_ctr = 0.5       # 0.5 → contribution 0.5*0.1=0.05
    score = AnalyticsService._compute_engagement_score(tp)
    assert score == pytest.approx(0.5, abs=1e-4)


# ---------------------------------------------------------------------------
# OptimizationService
# ---------------------------------------------------------------------------

def _make_tp(platform="x", tone="authoritative", vertical="general",
             engagement_score=0.5, sample_count=10, avg_likes=500.0,
             avg_shares=200.0, avg_comments=50.0, avg_impressions=5000.0,
             avg_ctr=0.06, approve_rate=0.8, reject_rate=0.1) -> TemplatePerformance:
    tp = MagicMock(spec=TemplatePerformance)
    tp.platform = platform
    tp.tone = tone
    tp.content_vertical = vertical
    tp.engagement_score = engagement_score
    tp.sample_count = sample_count
    tp.avg_likes = avg_likes
    tp.avg_shares = avg_shares
    tp.avg_comments = avg_comments
    tp.avg_impressions = avg_impressions
    tp.avg_ctr = avg_ctr
    tp.approve_rate = approve_rate
    tp.reject_rate = reject_rate
    return tp


def _make_opt_service() -> OptimizationService:
    svc = object.__new__(OptimizationService)
    svc.db = AsyncMock()
    svc.repo = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_recommend_returns_ranked_list() -> None:
    svc = _make_opt_service()
    tp1 = _make_tp(tone="authoritative", engagement_score=0.7)
    tp2 = _make_tp(tone="casual", engagement_score=0.4)
    # repo returns already-sorted (by engagement_score desc)
    svc.repo.list_template_performance = AsyncMock(return_value=[tp1, tp2])

    recs = await svc.recommend(uuid.uuid4())

    assert len(recs) == 2
    assert recs[0].engagement_score == pytest.approx(0.7)
    assert isinstance(recs[0], ContentParameterRecommendation)


@pytest.mark.asyncio
async def test_recommend_top_n_limits_results() -> None:
    svc = _make_opt_service()
    tps = [_make_tp(tone=f"tone{i}", engagement_score=1.0 - i * 0.1) for i in range(10)]
    svc.repo.list_template_performance = AsyncMock(return_value=tps)

    recs = await svc.recommend(uuid.uuid4(), top_n=3)
    assert len(recs) == 3


@pytest.mark.asyncio
async def test_recommend_low_confidence_label_for_few_samples() -> None:
    svc = _make_opt_service()
    tp = _make_tp(sample_count=1)
    svc.repo.list_template_performance = AsyncMock(return_value=[tp])

    recs = await svc.recommend(uuid.uuid4())
    assert any("low_confidence" in r for r in recs[0].reasons)


@pytest.mark.asyncio
async def test_recommend_high_likes_reason() -> None:
    svc = _make_opt_service()
    tp = _make_tp(sample_count=10, avg_likes=1000)
    svc.repo.list_template_performance = AsyncMock(return_value=[tp])

    recs = await svc.recommend(uuid.uuid4())
    assert "high_likes" in recs[0].reasons


@pytest.mark.asyncio
async def test_recommend_passes_platform_filter() -> None:
    svc = _make_opt_service()
    svc.repo.list_template_performance = AsyncMock(return_value=[])

    await svc.recommend(uuid.uuid4(), platform="instagram")

    svc.repo.list_template_performance.assert_awaited_once()
    _, kwargs = svc.repo.list_template_performance.call_args
    assert kwargs.get("platform") == "instagram"


@pytest.mark.asyncio
async def test_best_tone_for_platform_returns_top_tone() -> None:
    svc = _make_opt_service()
    tp = _make_tp(platform="x", tone="witty", engagement_score=0.9)
    svc.repo.list_template_performance = AsyncMock(return_value=[tp])

    tone = await svc.best_tone_for_platform(uuid.uuid4(), "x")
    assert tone == "witty"


@pytest.mark.asyncio
async def test_best_tone_for_platform_returns_none_when_no_data() -> None:
    svc = _make_opt_service()
    svc.repo.list_template_performance = AsyncMock(return_value=[])

    tone = await svc.best_tone_for_platform(uuid.uuid4(), "tiktok")
    assert tone is None


@pytest.mark.asyncio
async def test_best_vertical_for_platform() -> None:
    svc = _make_opt_service()
    tp = _make_tp(platform="instagram", vertical="fashion")
    svc.repo.list_template_performance = AsyncMock(return_value=[tp])

    vertical = await svc.best_vertical_for_platform(uuid.uuid4(), "instagram")
    assert vertical == "fashion"


# ---------------------------------------------------------------------------
# Feedback loop wiring
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_snapshots_calls_update_template_performance() -> None:
    """sync_snapshots must feed each snapshot into update_template_performance."""
    svc = _make_service()
    post = _make_post()

    svc.publishing_repo.list_published_posts = AsyncMock(return_value=[post])
    svc.repo.get_snapshot_for_post = AsyncMock(return_value=None)
    svc.publishing_repo.get_token_for_account = AsyncMock(return_value=None)

    created_snap = MagicMock(spec=AnalyticsSnapshot)
    svc.repo.create_snapshot = AsyncMock(return_value=created_snap)

    # Spy on update_template_performance so we can assert it was called
    svc.update_template_performance = AsyncMock(return_value=MagicMock(spec=TemplatePerformance))

    with patch("backend.modules.analytics.service.get_metrics_provider", return_value=None):
        await svc.sync_snapshots(post.tenant_id)

    svc.update_template_performance.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_uses_optimization_recommended_tone() -> None:
    """When OptimizationService has data, generate() passes the recommended tone to the orchestrator."""
    from backend.modules.content_generation.service import ContentGenerationService
    from backend.modules.editorial_briefs.models import BriefStatus

    svc = object.__new__(ContentGenerationService)
    svc.db = AsyncMock()
    svc.repo = AsyncMock()
    svc.plan_repo = AsyncMock()
    svc.story_repo = AsyncMock()
    svc.audit = AsyncMock()
    svc.video_pipeline = AsyncMock()
    svc.llm = AsyncMock()

    tenant_id = uuid.uuid4()

    plan = MagicMock()
    plan.id = uuid.uuid4()
    plan.story_cluster_id = uuid.uuid4()
    plan.decision = "generate"
    plan.content_format = "text"
    plan.tone = "authoritative"
    plan.target_platforms = ["x"]
    plan.hashtags_strategy = "balanced"
    plan.recommended_cta = ""
    svc.plan_repo.get_content_plan = AsyncMock(return_value=plan)

    cluster = MagicMock()
    cluster.id = uuid.uuid4()
    cluster.headline = "Test headline"
    cluster.summary = "Test summary"
    cluster.primary_topic = "test"
    cluster.explainability = {"keywords": "test"}
    cluster.content_vertical = "technology"
    cluster.risk_level = "safe"
    svc.story_repo.get_cluster = AsyncMock(return_value=cluster)
    svc.story_repo.list_normalized_for_cluster = AsyncMock(return_value=[])

    brief = MagicMock()
    brief.status = BriefStatus.APPROVED.value
    brief.angle = ""
    brief.talking_points = []

    job = MagicMock()
    job.id = uuid.uuid4()
    job.grounding_bundle = {"headline": "Test headline", "summary": "Test summary", "topic": "test"}
    svc.repo.create_job = AsyncMock(return_value=job)

    orch_result = MagicMock()
    orch_result.reviewer.passed = True
    orch_result.reviewer.revised_draft = None
    orch_result.reviewer.model_dump.return_value = {"passed": True, "issues": []}
    orch_result.scorer.composite = 0.7
    orch_result.scorer.reasoning = "Good"
    orch_result.reviewer.issues = []
    orch_result.extractor.content_vertical = "technology"
    orch_result.extractor.risk_flags = []
    orch_result.planner.recommended_format = "text"
    orch_result.planner.target_platforms = ["x"]
    orch_result.planner.hook = "Test hook"
    orch_result.planner.model_dump.return_value = {
        "recommended_format": "text",
        "target_platforms": ["x"],
    }
    orch_result.writer.drafts = {"x": "Draft text"}
    orch_result.writer.model_dump.return_value = {"drafts": {"x": "Draft text"}}
    orch_result.optimizer.variants = ["variant_a"]
    orch_result.optimizer.recommended_variant_index = 0
    orch_result.final_draft = "Draft text"
    orch_result.recommended = True

    with (
        patch("backend.modules.content_generation.service.EditorialBriefRepository") as mock_brief_cls,
        patch("backend.modules.content_generation.service.ContentOrchestrator") as mock_orch_cls,
        patch("backend.modules.analytics.optimization.AnalyticsRepository") as _mock_analytics_repo,
        patch("backend.modules.content_generation.image_service.ImageGenerationService") as mock_image_cls,
        patch("backend.modules.content_generation.tts_service.TTSService") as mock_tts_cls,
    ):
        mock_brief_cls.return_value.get_by_cluster = AsyncMock(return_value=brief)
        mock_image_cls.return_value.generate_for_job = AsyncMock(return_value=None)
        mock_tts_cls.return_value.generate_for_job = AsyncMock(return_value=None)

        mock_orch = AsyncMock()
        mock_orch.run = AsyncMock(return_value=orch_result)
        mock_orch_cls.return_value = mock_orch

        # Patch OptimizationService inside the local import path
        with patch("backend.modules.analytics.optimization.OptimizationService.best_tone_for_platform",
                   new=AsyncMock(return_value="witty")):
            await svc.generate(tenant_id=tenant_id, plan_id=plan.id)

    call_kwargs = mock_orch.run.call_args[1]
    assert call_kwargs["tone"] == "witty", (
        f"Expected orchestrator tone='witty' (from OptimizationService), got '{call_kwargs['tone']}'"
    )


@pytest.mark.asyncio
async def test_generate_falls_back_to_plan_tone_when_no_optimization_data() -> None:
    """When OptimizationService returns None, generate() falls back to plan.tone."""
    from backend.modules.content_generation.service import ContentGenerationService
    from backend.modules.editorial_briefs.models import BriefStatus

    svc = object.__new__(ContentGenerationService)
    svc.db = AsyncMock()
    svc.repo = AsyncMock()
    svc.plan_repo = AsyncMock()
    svc.story_repo = AsyncMock()
    svc.audit = AsyncMock()
    svc.video_pipeline = AsyncMock()
    svc.llm = AsyncMock()

    tenant_id = uuid.uuid4()

    plan = MagicMock()
    plan.id = uuid.uuid4()
    plan.story_cluster_id = uuid.uuid4()
    plan.decision = "generate"
    plan.content_format = "text"
    plan.tone = "authoritative"
    plan.target_platforms = ["x"]
    plan.hashtags_strategy = "balanced"
    plan.recommended_cta = ""
    svc.plan_repo.get_content_plan = AsyncMock(return_value=plan)

    cluster = MagicMock()
    cluster.id = uuid.uuid4()
    cluster.headline = "Test headline"
    cluster.summary = "Test summary"
    cluster.primary_topic = "test"
    cluster.explainability = {"keywords": "test"}
    cluster.content_vertical = "general"
    cluster.risk_level = "safe"
    svc.story_repo.get_cluster = AsyncMock(return_value=cluster)
    svc.story_repo.list_normalized_for_cluster = AsyncMock(return_value=[])

    brief = MagicMock()
    brief.status = BriefStatus.APPROVED.value
    brief.angle = ""
    brief.talking_points = []

    job = MagicMock()
    job.id = uuid.uuid4()
    job.grounding_bundle = {"headline": "Test headline", "summary": "Test summary", "topic": "test"}
    svc.repo.create_job = AsyncMock(return_value=job)

    orch_result = MagicMock()
    orch_result.reviewer.passed = True
    orch_result.reviewer.model_dump.return_value = {"passed": True, "issues": []}
    orch_result.scorer.composite = 0.6
    orch_result.scorer.reasoning = "OK"
    orch_result.reviewer.issues = []
    orch_result.extractor.content_vertical = "general"
    orch_result.extractor.risk_flags = []
    orch_result.planner.target_platforms = ["x"]
    orch_result.planner.recommended_format = "text"
    orch_result.planner.hook = "Fallback hook"
    orch_result.planner.model_dump.return_value = {
        "recommended_format": "text",
        "target_platforms": ["x"],
    }
    orch_result.writer.drafts = {"x": "Draft text"}
    orch_result.writer.model_dump.return_value = {"drafts": {"x": "Draft text"}}
    orch_result.optimizer.variants = []
    orch_result.optimizer.recommended_variant_index = 0
    orch_result.final_draft = "Draft text"

    with (
        patch("backend.modules.content_generation.service.EditorialBriefRepository") as mock_brief_cls,
        patch("backend.modules.content_generation.service.ContentOrchestrator") as mock_orch_cls,
        patch("backend.modules.content_generation.image_service.ImageGenerationService") as mock_image_cls,
        patch("backend.modules.content_generation.tts_service.TTSService") as mock_tts_cls,
    ):
        mock_brief_cls.return_value.get_by_cluster = AsyncMock(return_value=brief)
        mock_image_cls.return_value.generate_for_job = AsyncMock(return_value=None)
        mock_tts_cls.return_value.generate_for_job = AsyncMock(return_value=None)

        mock_orch = AsyncMock()
        mock_orch.run = AsyncMock(return_value=orch_result)
        mock_orch_cls.return_value = mock_orch

        # OptimizationService returns None (no historical data)
        with patch("backend.modules.analytics.optimization.OptimizationService.best_tone_for_platform",
                   new=AsyncMock(return_value=None)):
            await svc.generate(tenant_id=tenant_id, plan_id=plan.id)

    call_kwargs = mock_orch.run.call_args[1]
    assert call_kwargs["tone"] == "authoritative", (
        f"Expected fallback to plan.tone='authoritative', got '{call_kwargs['tone']}'"
    )
