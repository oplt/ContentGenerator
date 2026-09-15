"""Phase 16 — regression + architecture enforcement map.

Each Phase 16 guard must keep an owning automated check. Feature tests stay with
their phases; this module fails CI if a guard loses its owner.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "docs" / "benchmarks" / "baseline.json"
FRONTEND = REPO_ROOT / "frontend"

# guard_id -> owning artifacts (paths relative to repo root)
PHASE16_GUARDS: dict[str, tuple[str, ...]] = {
    "frontend_production_build": ("frontend/src/app/bundleBudget.test.ts",),
    "no_unresolved_imports": (
        "backend/tests/test_app_smoke.py",
        "frontend/src/api/parityManifest.test.ts",
    ),
    "production_line_budget": ("backend/tests/test_file_line_budget.py",),
    "routers_no_commit": ("backend/tests/test_transaction_architecture.py",),
    "services_repos_commit_policy": ("backend/tests/test_transaction_architecture.py",),
    "db_query_budgets": (
        "backend/tests/benchmarks/test_baseline_harness.py",
        "backend/tests/test_phase2_query_precision.py",
    ),
    "publishing_stale_no_n1": ("backend/tests/test_phase2_query_precision.py",),
    "ingestion_batch_insert_budget": ("backend/tests/test_phase2_query_precision.py",),
    "route_parity": (
        "backend/tests/test_route_parity.py",
        "frontend/src/api/parityManifest.test.ts",
    ),
    "cache_key_tenant_isolation": ("backend/tests/test_tenant_cache.py",),
    "cache_namespace_safety": (
        "backend/tests/test_phase5_cache.py",
        "backend/tests/test_tenant_cache.py",
    ),
    "cancellation_propagation": ("backend/tests/test_phase4_http_policy.py",),
    "retry_after_http_date": (
        "backend/tests/test_phase4_http_policy.py",
        "backend/tests/test_http_client.py",
    ),
    "publishing_idempotency": ("backend/tests/test_publishing_idempotency.py",),
    "worker_retry_idempotency": (
        "backend/tests/test_celery_policy.py",
        "backend/tests/test_worker_recovery.py",
    ),
    "frontend_bundle_regression": ("frontend/src/app/bundleBudget.test.ts",),
    "web_vitals_regression": ("backend/tests/benchmarks/test_baseline_harness.py",),
}


@pytest.mark.parametrize("guard_id", sorted(PHASE16_GUARDS))
def test_phase16_guard_has_owning_modules(guard_id: str) -> None:
    for relative in PHASE16_GUARDS[guard_id]:
        path = REPO_ROOT / relative
        assert path.is_file(), f"{guard_id}: missing {relative} -> {path}"


def test_phase16_covers_all_prompt_guards() -> None:
    required = {
        "frontend_production_build",
        "no_unresolved_imports",
        "production_line_budget",
        "routers_no_commit",
        "services_repos_commit_policy",
        "db_query_budgets",
        "publishing_stale_no_n1",
        "ingestion_batch_insert_budget",
        "route_parity",
        "cache_key_tenant_isolation",
        "cache_namespace_safety",
        "cancellation_propagation",
        "retry_after_http_date",
        "publishing_idempotency",
        "worker_retry_idempotency",
        "frontend_bundle_regression",
        "web_vitals_regression",
    }
    assert set(PHASE16_GUARDS) == required


def test_critical_backend_modules_import() -> None:
    """Unresolved production imports fail here before full mypy."""
    for module in (
        "backend.api.main",
        "backend.core.http",
        "backend.core.domain_metrics",
        "backend.db.session",
        "backend.workers.celery_app",
    ):
        importlib.import_module(module)


def test_baseline_query_budgets_are_meaningful() -> None:
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    critical = {
        "duplicate_detection": 2,
        "source_ingestion": 2,
        "publishing_claim_recovery": 3,
        "major_list_endpoints": 5,
    }
    for scenario_id, ceiling in critical.items():
        scenario = payload["scenarios"][scenario_id]
        observed = scenario["observed"]["db_query_count"]
        budget = scenario["thresholds"]["db_query_count_max"]
        assert isinstance(budget, int)
        assert budget >= observed
        assert budget <= ceiling, f"{scenario_id}: budget {budget} exceeds architectural ceiling {ceiling}"


def test_frontend_package_scripts_include_build() -> None:
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    assert "build" in package.get("scripts", {})
