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
    "auth_session": ("test_auth_remember_me_cookies.py", "test_auth_sign_in_http.py"),
    "db_pooling_transactions": ("test_db_pooling.py", "test_transaction_architecture.py"),
    "http_provider_budgets": ("test_http_client.py", "test_phase4_http_policy.py"),
    "tenant_cache": ("test_tenant_cache.py", "test_phase5_cache.py"),
    "source_scheduling": ("test_source_scheduling_dedupe.py",),
    "analytics_batching": ("test_analytics_sync_batching.py",),
    "api_contracts_parity": ("test_route_parity.py", "test_app_smoke.py"),
    "dormant_registration": ("test_dormant_modules.py",),
    "domain_metrics": (
        "test_domain_metrics.py",
        "test_phase15_observability.py",
        "test_workflow_observability.py",
        "test_workflow_phase19_observability.py",
    ),
    "rollout_gates": ("test_rollout_gates.py",),
    "migration_drift": ("test_migration_drift.py",),
    "worker_recovery": ("test_worker_recovery.py",),
    "performance_baselines": ("benchmarks/test_baseline_harness.py",),
    "regression_manifest": ("test_regression_manifest.py",),
    "dead_code_hygiene": ("test_dead_code_hygiene.py",),
    "module_decomposition": ("test_module_decomposition.py",),
    "query_precision": ("test_phase2_query_precision.py",),
    "session_residency": ("test_phase3_residency.py",),
    "line_budget": ("test_file_line_budget.py",),
    "worker_capacity": ("test_phase14_worker_capacity.py",),
    "architecture_enforcement": (
        "test_phase16_architecture_guards.py",
        "test_phase16_regression_matrix.py",
    ),
    "ops_phase_regressions": (
        "test_phase13_db_tx_lifetime.py",
        "test_phase14_task_traceability.py",
        "test_phase15_social_accounts_profile.py",
        "test_workflow_listings_regression.py",
        "test_correlation_id_propagation.py",
        "test_tenant_context_on_errors.py",
        "test_briefs_write_permission.py",
        "test_audit_logs_http.py",
        "test_enrichment_llm_cache.py",
        "test_chess_provenance.py",
        "test_chess_source_rules.py",
        "test_chess_provider_http_reliability.py",
        "test_chess_provider_cache.py",
        "test_chess_migrations.py",
        "test_chess_catalog_jobs.py",
        "test_chess_tenant_isolation.py",
        "test_chess_phase25_coverage.py",
        "test_chess_section30_coverage.py",
        "test_chess_dependency_policy.py",
        "test_chess_backend_structure.py",
        "test_chess_configuration.py",
        "test_chess_observability.py",
        "test_chess_documentation.py",
    ),
    "workflow_automation": (
        "test_workflow_engine.py",
        "test_workflow_graph_compiler.py",
        "test_workflow_scheduler.py",
        "test_workflow_approval_resume.py",
        "test_workflow_security.py",
        "test_workflow_strategy.py",
        "test_workflow_phase18_production_grade.py",
        "test_workflow_phase18_regression_matrix.py",
    ),
    "workflow_production_gaps": (
        "test_workflow_production_gaps.py",
        "test_workflow_node_claims.py",
        "test_workflow_retry.py",
        "test_workflow_port_bindings.py",
        "test_workflow_phase4_control_flow.py",
        "test_workflow_control_flow.py",
        "test_workflow_phase5_durable_waits.py",
        "test_workflow_phase6_automation_integrity.py",
        "test_workflow_phase7_scheduler_lifecycle.py",
        "test_workflow_phase8_capability_trust.py",
        "test_workflow_phase9_approval_policy.py",
        "test_workflow_phase10_content_variants.py",
        "test_workflow_phase11_canonical_content.py",
        "test_workflow_phase12_implementation_status.py",
        "test_workflow_chess_intelligence_nodes.py",
        "test_workflow_phase20_perf_retention.py",
        "test_workflow_automations_api.py",
    ),
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
        "architecture_enforcement",
        "query_precision",
        "line_budget",
        "workflow_automation",
        "workflow_production_gaps",
        "ops_phase_regressions",
    ):
        assert required in themes
