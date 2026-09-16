"""Ops Phase 16 — map prompt regression requirements to owning automated tests."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_TESTS = REPO_ROOT / "backend" / "tests"
FRONTEND = REPO_ROOT / "frontend"

# requirement_id -> test module paths relative to repo root
PHASE16_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "migrations_empty_db_upgrade": ("backend/tests/test_migration_drift.py",),
    "migrations_previous_schema_upgrade": ("backend/tests/test_migration_drift.py",),
    "alembic_revision_at_head": (
        "backend/tests/test_migration_drift.py",
        "backend/tests/test_schema_revision.py",
    ),
    "workflow_tables_exist": ("backend/tests/test_migration_drift.py",),
    "workflow_definitions_list": ("backend/tests/test_workflow_listings_regression.py",),
    "automations_list": (
        "backend/tests/test_workflow_listings_regression.py",
        "backend/tests/test_workflow_automations_api.py",
    ),
    "workflow_runs_list": ("backend/tests/test_workflow_listings_regression.py",),
    "scheduler_tick_succeeds": ("backend/tests/test_workflow_scheduler.py",),
    "scheduler_no_double_claim": (
        "backend/tests/test_workflow_scheduler.py",
        "backend/tests/test_workflow_scheduler_pg.py",
    ),
    "tenant_isolation": (
        "backend/tests/test_workflow_domain_models.py",
        "backend/tests/test_workflow_strategy.py",
        "backend/tests/test_account_selection.py",
    ),
    "soft_deleted_excluded": ("backend/tests/test_workflow_listings_regression.py",),
    "correlation_id_propagation": ("backend/tests/test_correlation_id_propagation.py",),
    "tenant_id_on_exception_paths": ("backend/tests/test_tenant_context_on_errors.py",),
    "frontend_no_retry_4xx": (
        "frontend/src/lib/queryRetry.test.ts",
        "frontend/src/lib/queryClient.test.ts",
    ),
    "briefs_rbac": (
        "backend/tests/test_briefs_write_permission.py",
        "frontend/src/features/auth/access.test.ts",
    ),
    "audit_logs_api_contract": ("backend/tests/test_audit_logs_http.py",),
    "ingestion_idempotent": (
        "backend/tests/test_phase3_residency.py",
        "backend/tests/test_source_scheduling_dedupe.py",
        "backend/tests/test_phase14_task_traceability.py",
    ),
    "enrichment_llm_cache_invalidation": ("backend/tests/test_enrichment_llm_cache.py",),
    "db_tx_outside_llm": ("backend/tests/test_phase13_db_tx_lifetime.py",),
    "duplicate_exception_logging": ("backend/tests/test_duplicate_exception_logging.py",),
    "architecture_guards_manifest": ("backend/tests/test_phase16_architecture_guards.py",),
    "regression_manifest": ("backend/tests/test_regression_manifest.py",),
}


@pytest.mark.parametrize("requirement_id", sorted(PHASE16_REQUIREMENTS))
def test_phase16_requirement_has_owning_tests(requirement_id: str) -> None:
    for relative in PHASE16_REQUIREMENTS[requirement_id]:
        path = REPO_ROOT / relative
        assert path.is_file(), f"{requirement_id}: missing {relative}"


def test_phase16_covers_prompt_minimum_list() -> None:
    required = {
        "migrations_empty_db_upgrade",
        "migrations_previous_schema_upgrade",
        "alembic_revision_at_head",
        "workflow_tables_exist",
        "workflow_definitions_list",
        "automations_list",
        "workflow_runs_list",
        "scheduler_tick_succeeds",
        "scheduler_no_double_claim",
        "tenant_isolation",
        "soft_deleted_excluded",
        "correlation_id_propagation",
        "tenant_id_on_exception_paths",
        "frontend_no_retry_4xx",
        "briefs_rbac",
        "audit_logs_api_contract",
        "ingestion_idempotent",
        "enrichment_llm_cache_invalidation",
    }
    assert required <= set(PHASE16_REQUIREMENTS)


def test_migration_drift_declares_integration_upgrade_tests() -> None:
    source = (BACKEND_TESTS / "test_migration_drift.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "test_alembic_upgrade_head_on_disposable_db" in names
    assert "test_alembic_upgrade_from_previous_revision" in names
    assert "test_workflow_tables_exist_after_upgrade" in names


def test_scheduler_owns_double_claim_tests() -> None:
    scheduler = (BACKEND_TESTS / "test_workflow_scheduler.py").read_text(encoding="utf-8")
    assert "test_claim_occurrence_second_worker_loses" in scheduler
    assert "test_concurrent_claim_occurrence_only_one_wins" in scheduler
    pg = (BACKEND_TESTS / "test_workflow_scheduler_pg.py").read_text(encoding="utf-8")
    assert "test_postgres_concurrent_claim_due_skip_locked" in pg
