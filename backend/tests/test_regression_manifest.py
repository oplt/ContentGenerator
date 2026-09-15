"""
Regression suite manifest (T8.2).

Ensures critical risk areas keep an owning automated test module. Feature tests
stay with their tasks; this file only orchestrates coverage presence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent

# risk_area -> required test module filenames (must exist under backend/tests/)
REGRESSION_MANIFEST: dict[str, tuple[str, ...]] = {
    "publish_crash_idempotency": ("test_publishing_idempotency.py",),
    "tenant_account_isolation": ("test_account_selection.py", "test_account_ops.py"),
    "social_account_model": ("test_social_account_consolidation.py",),
    "celery_worker_policy": ("test_celery_policy.py",),
    "db_pooling_transactions": ("test_db_pooling.py",),
    "http_provider_budgets": ("test_http_client.py",),
    "tenant_cache": ("test_tenant_cache.py",),
    "source_scheduling": ("test_source_scheduling_dedupe.py",),
    "analytics_batching": ("test_analytics_sync_batching.py",),
    "api_contracts_parity": ("test_route_parity.py", "test_app_smoke.py"),
    "dormant_registration": ("test_dormant_modules.py",),
    "domain_metrics": ("test_domain_metrics.py",),
    "rollout_gates": ("test_rollout_gates.py",),
    "migration_drift": ("test_migration_drift.py",),
    "worker_recovery": ("test_worker_recovery.py",),
    "performance_baselines": ("benchmarks/test_baseline_harness.py",),
    "regression_manifest": ("test_regression_manifest.py",),
    "dead_code_hygiene": ("test_dead_code_hygiene.py",),
    "module_decomposition": ("test_module_decomposition.py",),
}


@pytest.mark.parametrize("risk_area", sorted(REGRESSION_MANIFEST))
def test_risk_area_has_owning_modules(risk_area: str) -> None:
    for relative in REGRESSION_MANIFEST[risk_area]:
        path = TESTS / relative
        assert path.is_file(), f"{risk_area}: missing {relative}"


def test_manifest_covers_acceptance_themes() -> None:
    themes = set(REGRESSION_MANIFEST)
    for required in (
        "publish_crash_idempotency",
        "tenant_account_isolation",
        "celery_worker_policy",
        "migration_drift",
        "api_contracts_parity",
        "performance_baselines",
        "rollout_gates",
    ):
        assert required in themes
