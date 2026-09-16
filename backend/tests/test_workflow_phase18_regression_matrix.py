"""Phase 18 — map prompt production-grade scenarios to owning tests."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_TESTS = REPO_ROOT / "backend" / "tests"

# requirement_id -> test module paths relative to repo root
PHASE18_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "concurrency_two_workers_one_claim": (
        "backend/tests/test_workflow_node_claims.py",
        "backend/tests/test_workflow_phase18_production_grade.py",
    ),
    "celery_task_redelivery_one_side_effect": (
        "backend/tests/test_workflow_phase18_production_grade.py",
        "backend/tests/test_workflow_node_claims.py",
    ),
    "crash_recovery_expired_claim": (
        "backend/tests/test_workflow_node_claims.py",
        "backend/tests/test_workflow_phase18_production_grade.py",
    ),
    "publish_node_redelivery_no_duplicate": (
        "backend/tests/test_workflow_phase18_production_grade.py",
        "backend/tests/test_workflow_strategy.py",
        "backend/tests/test_publishing_idempotency.py",
    ),
    "approval_revise_then_approve_once": (
        "backend/tests/test_workflow_phase18_production_grade.py",
        "backend/tests/test_workflow_phase9_approval_policy.py",
        "backend/tests/test_workflow_approval_resume.py",
    ),
    "durable_delay_survives_restart": (
        "backend/tests/test_workflow_phase5_durable_waits.py",
        "backend/tests/test_workflow_phase18_production_grade.py",
        "backend/tests/test_workflow_control_flow.py",
    ),
    "scheduler_two_ticks_one_run": (
        "backend/tests/test_workflow_scheduler.py",
        "backend/tests/test_workflow_scheduler_pg.py",
        "backend/tests/test_workflow_phase18_production_grade.py",
    ),
    "branching_condition_merge_skip_fail": (
        "backend/tests/test_workflow_phase4_control_flow.py",
        "backend/tests/test_workflow_control_flow.py",
        "backend/tests/test_workflow_phase18_production_grade.py",
    ),
    "tenant_isolation_cross_entity": (
        "backend/tests/test_workflow_domain_models.py",
        "backend/tests/test_workflow_execution_state.py",
        "backend/tests/test_workflow_strategy.py",
        "backend/tests/test_workflow_phase18_production_grade.py",
    ),
    "e2e_chess_daily_automation": (
        "backend/tests/test_workflow_phase18_production_grade.py",
        "backend/tests/test_workflow_strategy.py",
    ),
    "e2e_technology_automation": (
        "backend/tests/test_workflow_phase18_production_grade.py",
        "backend/tests/test_workflow_strategy.py",
    ),
}


@pytest.mark.parametrize("requirement_id", sorted(PHASE18_REQUIREMENTS))
def test_phase18_requirement_has_owning_tests(requirement_id: str) -> None:
    for relative in PHASE18_REQUIREMENTS[requirement_id]:
        path = REPO_ROOT / relative
        assert path.is_file(), f"{requirement_id}: missing {relative}"


def test_phase18_covers_prompt_minimum_list() -> None:
    required = {
        "concurrency_two_workers_one_claim",
        "celery_task_redelivery_one_side_effect",
        "crash_recovery_expired_claim",
        "publish_node_redelivery_no_duplicate",
        "approval_revise_then_approve_once",
        "durable_delay_survives_restart",
        "scheduler_two_ticks_one_run",
        "branching_condition_merge_skip_fail",
        "tenant_isolation_cross_entity",
        "e2e_chess_daily_automation",
        "e2e_technology_automation",
    }
    assert required <= set(PHASE18_REQUIREMENTS)


def test_phase18_behavioral_file_declares_acceptance_tests() -> None:
    source = (BACKEND_TESTS / "test_workflow_phase18_production_grade.py").read_text(
        encoding="utf-8"
    )
    for name in (
        "test_celery_redelivery_executes_node_once",
        "test_publish_redelivery_does_not_duplicate_jobs",
        "test_approval_revise_then_approve_resumes_once",
        "test_durable_delay_survives_session_restart",
        "test_scheduler_double_tick_one_workflow_run",
        "test_branching_condition_and_merge_semantics",
        "test_tenant_isolation_run_resume_variant",
        "test_e2e_chess_daily_automation_dry_run",
        "test_e2e_technology_automation_dry_run",
    ):
        assert f"def {name}" in source, name
