"""Characterization tests for T7.1 responsibility-based module decomposition."""

from __future__ import annotations

import ast
from pathlib import Path

from backend.modules.analytics.metrics import AnalyticsMetrics
from backend.modules.analytics.overview_builder import aggregate_snapshot_charts, build_learning_log
from backend.modules.analytics.service import AnalyticsService
from backend.modules.approvals.service import ApprovalService
from backend.modules.approvals import telegram_callbacks, webhook_processing
from backend.modules.content_generation.asset_specs import build_platform_asset_specs
from backend.modules.content_generation.service import ContentGenerationService
from backend.modules.publishing.attempt_lifecycle import PublishAttemptLifecycle
from backend.modules.publishing.job_executor import publish_job
from backend.modules.publishing.service import PublishingService
from backend.modules.source_ingestion.fetch_cache import (
    articles_from_cache,
    describe_fetch_error,
    save_cache,
    semantic_duplicate,
)
from backend.modules.source_ingestion.service import SourceIngestionService
from backend.modules.story_intelligence.scoring import ClusterScorer
from backend.modules.story_intelligence.service import StoryIntelligenceService
from backend.modules.trending_repos.github_client import GitHubTrendingClient
from backend.modules.trending_repos.product_ideas import ProductIdeasGenerator
from backend.modules.trending_repos.service import TrendingReposService
from backend.workers import tasks as task_module
from backend.workers.celery_app import celery_app
from backend.workers.task_policy import TASK_POLICIES


def test_celery_task_names_remain_stable() -> None:
    registered = sorted(
        name for name in celery_app.tasks if name.startswith("backend.workers.tasks.")
    )
    assert registered == sorted(TASK_POLICIES.keys())
    for name in TASK_POLICIES:
        short = name.rsplit(".", 1)[-1]
        assert hasattr(task_module, short), f"facade missing {short}"


def test_facade_service_classes_remain_importable() -> None:
    for cls in (
        PublishingService,
        AnalyticsService,
        SourceIngestionService,
        ContentGenerationService,
        ApprovalService,
        StoryIntelligenceService,
        TrendingReposService,
    ):
        assert cls.__module__.endswith(".service")


def test_publishing_attempt_key_facade() -> None:
    job = type("Job", (), {"idempotency_key": "content-1:x"})()
    assert PublishingService.build_attempt_key(job, 1) == "content-1:x:attempt:1"
    assert PublishAttemptLifecycle.build_attempt_key(job, 2) == "content-1:x:attempt:2"


def test_collaborator_modules_exist_and_parse() -> None:
    root = Path(__file__).resolve().parents[1]
    modules = [
        "modules/publishing/attempt_lifecycle.py",
        "modules/publishing/job_executor.py",
        "modules/analytics/metrics.py",
        "modules/analytics/overview_builder.py",
        "modules/source_ingestion/fetch_cache.py",
        "modules/content_generation/asset_specs.py",
        "modules/approvals/webhook_processing.py",
        "modules/approvals/telegram_callbacks.py",
        "modules/story_intelligence/scoring.py",
        "modules/trending_repos/github_client.py",
        "modules/trending_repos/product_ideas.py",
        "workers/task_defs/ingestion.py",
        "workers/task_defs/publishing.py",
        "workers/task_defs/trending.py",
    ]
    for rel in modules:
        path = root / rel
        assert path.is_file(), rel
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_named_collaborators_exported() -> None:
    assert callable(publish_job)
    assert callable(aggregate_snapshot_charts)
    assert callable(build_learning_log)
    assert callable(build_platform_asset_specs)
    assert callable(webhook_processing.handle_webhook)
    assert callable(telegram_callbacks.handle_telegram_callback)
    assert callable(GitHubTrendingClient.fetch_from_github)
    assert callable(ProductIdeasGenerator.generate_product_ideas)
    assert callable(ClusterScorer._score_cluster)
    assert callable(semantic_duplicate)
    assert callable(articles_from_cache)
    assert callable(save_cache)
    assert callable(describe_fetch_error)
    assert AnalyticsMetrics.__name__ == "AnalyticsMetrics"
