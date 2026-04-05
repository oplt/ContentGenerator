from __future__ import annotations

import warnings

from sqlalchemy.exc import SAWarning

from backend.db import model_registry  # noqa: F401
from backend.db.base import Base


def test_required_tables_exist_in_metadata():
    required_tables = {
        "tenants",
        "users",
        "tenant_users",
        "roles",
        "permissions",
        "social_accounts",
        "social_account_tokens",
        "brand_profiles",
        "sources",
        "source_fetch_runs",
        "raw_articles",
        "normalized_articles",
        "story_clusters",
        "story_cluster_articles",
        "trend_scores",
        "content_plans",
        "content_jobs",
        "content_revisions",
        "generated_assets",
        "approval_requests",
        "approval_messages",
        "publishing_jobs",
        "published_posts",
        "analytics_snapshots",
        "webhooks_inbox",
        "task_executions",
        "audit_logs",
    }

    assert required_tables.issubset(Base.metadata.tables.keys())


def test_metadata_has_no_unresolvable_fk_cycles():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", SAWarning)
        list(Base.metadata.sorted_tables)

    cycle_warnings = [
        warning
        for warning in caught
        if issubclass(warning.category, SAWarning)
        and "unresolvable cycles" in str(warning.message)
    ]

    assert not cycle_warnings
