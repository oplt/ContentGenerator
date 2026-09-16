"""Phase 0 — roadmap gap regression suite (prompt.txt P1–P6).

Phase 1–6 gaps are asserted green.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
from sqlalchemy.orm import Mapper

from backend.modules.workflows.run_models import WorkflowNodeRun

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_INPUTS = REPO_ROOT / "backend/modules/workflows/engine_inputs.py"
ENGINE = REPO_ROOT / "backend/modules/workflows/engine.py"

PHASE1_CLAIM_COLUMNS = (
    "claim_token",
    "claim_expires_at",
    "claimed_at",
    "worker_task_id",
    "next_attempt_at",
    "last_heartbeat_at",
    "execution_key",
)


def _workflow_node_run_column_names() -> set[str]:
    mapper: Mapper[WorkflowNodeRun] = WorkflowNodeRun.__mapper__  # type: ignore[assignment]
    return {col.key for col in mapper.columns}


@pytest.mark.workflow_production_gap
def test_workflow_node_run_has_atomic_claim_fields() -> None:
    columns = _workflow_node_run_column_names()
    missing = [name for name in PHASE1_CLAIM_COLUMNS if name not in columns]
    assert not missing, f"missing claim columns: {missing}"


@pytest.mark.workflow_production_gap
def test_workflow_run_repository_exposes_node_claim_api() -> None:
    from backend.modules.workflows import run_repository

    for name in (
        "claim_ready_node",
        "renew_node_claim",
        "release_node_claim",
        "complete_node",
        "fail_node",
    ):
        assert hasattr(run_repository, name), f"missing run_repository.{name}"


@pytest.mark.workflow_production_gap
def test_execute_workflow_node_task_is_registered() -> None:
    from backend.workers import tasks

    assert hasattr(tasks, "execute_workflow_node_task")


@pytest.mark.workflow_production_gap
def test_workflow_node_claim_recovery_task_is_registered() -> None:
    from backend.workers import tasks

    assert hasattr(tasks, "recover_stale_workflow_node_runs_task")


@pytest.mark.workflow_production_gap
def test_engine_advance_does_not_inline_execute_ready_nodes() -> None:
    source = ENGINE.read_text(encoding="utf-8")
    assert "execute_ready_node" not in source, (
        "WorkflowEngine.advance must not call execute_ready_node inline"
    )


@pytest.mark.workflow_production_gap
def test_engine_execute_populates_task_execution_id() -> None:
    from backend.modules.workflows import engine_execute

    source = inspect.getsource(engine_execute.execute_ready_node)
    assert "task_execution_id" in source


@pytest.mark.workflow_production_gap
def test_workflow_node_run_persists_retry_state_fields() -> None:
    columns = _workflow_node_run_column_names()
    for name in ("next_attempt_at", "last_error", "error_class"):
        assert name in columns, f"missing {name}"


@pytest.mark.workflow_production_gap
def test_engine_inputs_avoids_node_type_switch_routing() -> None:
    source = ENGINE_INPUTS.read_text(encoding="utf-8")
    matches = re.findall(r'if\s+node_type\s*==\s*"', source)
    assert len(matches) == 0, (
        f"engine_inputs still has {len(matches)} node_type branches; "
        "use ports/bindings instead"
    )


@pytest.mark.workflow_production_gap
def test_workflow_node_run_has_iteration_key() -> None:
    columns = _workflow_node_run_column_names()
    assert "iteration_key" in columns


@pytest.mark.workflow_production_gap
def test_merge_any_readiness_does_not_require_all_success() -> None:
    from backend.modules.workflows.engine_ready import is_ready
    from backend.modules.workflows.graph_schema import WorkflowGraph
    from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowNodeRunStatus
    import uuid

    graph = WorkflowGraph.model_validate(
        {
            "nodes": [
                {"id": "a", "type": "summarize", "version": 1, "config": {}},
                {"id": "b", "type": "summarize", "version": 1, "config": {}},
                {"id": "merge", "type": "merge", "version": 1, "config": {"mode": "any"}},
            ],
            "edges": [
                {"source": "a", "target": "merge"},
                {"source": "b", "target": "merge"},
            ],
        }
    )
    tid, rid = uuid.uuid4(), uuid.uuid4()
    runs = {
        "a": WorkflowNodeRun(
            tenant_id=tid,
            workflow_run_id=rid,
            node_id="a",
            node_type="summarize",
            node_version=1,
            status=WorkflowNodeRunStatus.SUCCEEDED.value,
        ),
        "b": WorkflowNodeRun(
            tenant_id=tid,
            workflow_run_id=rid,
            node_id="b",
            node_type="summarize",
            node_version=1,
            status=WorkflowNodeRunStatus.PENDING.value,
        ),
        "merge": WorkflowNodeRun(
            tenant_id=tid,
            workflow_run_id=rid,
            node_id="merge",
            node_type="merge",
            node_version=1,
            status=WorkflowNodeRunStatus.PENDING.value,
        ),
    }
    assert is_ready("merge", graph=graph, node_runs=runs) is True


@pytest.mark.workflow_production_gap
def test_workflow_wait_model_exists() -> None:
    from backend.modules.workflows.run_models import WorkflowWait

    columns = {col.key for col in WorkflowWait.__mapper__.columns}
    for name in (
        "wake_at",
        "event_key",
        "wait_type",
        "resume_token",
        "status",
        "timeout_action",
    ):
        assert name in columns, f"missing WorkflowWait.{name}"


@pytest.mark.workflow_production_gap
def test_wake_due_workflow_waits_task_is_registered() -> None:
    from backend.workers import tasks

    assert hasattr(tasks, "wake_due_workflow_waits_task")


@pytest.mark.workflow_production_gap
def test_automation_integrity_helpers_exist() -> None:
    from backend.modules.workflows import automation_integrity as mod

    for name in (
        "require_active_brand",
        "require_version_for_definition",
        "authorize_brand_linked_accounts",
    ):
        assert hasattr(mod, name)


@pytest.mark.workflow_production_gap
def test_workflow_versions_have_definition_id_unique() -> None:
    from backend.modules.workflows.models import WorkflowVersion

    names = {c.name for c in WorkflowVersion.__table__.constraints if getattr(c, "name", None)}
    assert "uq_workflow_versions_tenant_definition_id" in names


@pytest.mark.workflow_production_gap
def test_scheduler_sync_schedule_state_exists() -> None:
    from backend.modules.workflows.scheduler import AutomationScheduler

    assert hasattr(AutomationScheduler, "sync_schedule_state")


@pytest.mark.workflow_production_gap
def test_occurrence_succeeded_status_and_sync() -> None:
    from backend.modules.workflows.models import AutomationOccurrenceStatus
    from backend.modules.workflows import occurrence_sync

    assert AutomationOccurrenceStatus.SUCCEEDED.value == "succeeded"
    assert hasattr(occurrence_sync, "sync_occurrence_for_run")


@pytest.mark.workflow_production_gap
def test_runtime_compile_context_builder_exists() -> None:
    from backend.modules.workflows import capability_context as mod
    from backend.modules.workflows.graph_schema import RuntimeClientContext

    assert hasattr(mod, "build_runtime_compile_context")
    assert hasattr(mod, "client_context_to_seed")
    # Capability maps must not be accepted on the client runtime binding.
    fields = set(RuntimeClientContext.model_fields)
    assert "account_capabilities" not in fields
    assert "account_platform_capabilities" not in fields


@pytest.mark.workflow_production_gap
def test_authorize_runtime_bindings_exists() -> None:
    from backend.modules.workflows import runtime_bindings as mod

    assert hasattr(mod, "authorize_runtime_bindings")


@pytest.mark.workflow_production_gap
def test_approval_required_false_and_delivery_service() -> None:
    from backend.modules.workflows.approval_delivery import ApprovalDeliveryService
    from backend.modules.workflows.nodes.approval import ApprovalConfig, ApprovalNode
    import inspect

    assert hasattr(ApprovalDeliveryService, "deliver")
    source = inspect.getsource(ApprovalNode.execute)
    assert "not_required" in source
    assert ApprovalConfig.model_fields["required"].default is True


@pytest.mark.workflow_production_gap
def test_content_variant_model_and_publish_link() -> None:
    from backend.modules.content_generation.models import ContentVariant, ContentVariantTarget
    from backend.modules.content_generation.variant_store import ContentVariantStore
    from backend.modules.publishing.models import PublishingJob
    from backend.modules.publishing.schemas import PublishNowRequest
    from backend.modules.workflows.nodes.platform_transform import PlatformTransformOutput
    from backend.modules.workflows.nodes.publishing import PublishInput

    assert ContentVariant.__tablename__ == "content_variants"
    assert ContentVariantTarget.__tablename__ == "content_variant_targets"
    assert hasattr(ContentVariantStore, "upsert_variant")
    assert "content_variant_id" in PublishingJob.__table__.c
    assert "content_variant_ids" in PublishNowRequest.model_fields
    assert "provider_payload" not in PublishNowRequest.model_fields
    assert "variant_ids" in PlatformTransformOutput.model_fields
    assert "content_variant_ids" in PublishInput.model_fields


@pytest.mark.workflow_production_gap
def test_canonical_content_node_wraps_domain_service() -> None:
    import inspect

    from backend.modules.content_generation import canonical as canonical_mod
    from backend.modules.workflows.nodes.canonical_content import GenerateCanonicalContentNode
    from backend.modules.workflows.nodes.text import GenerateTextNode
    from backend.modules.workflows.testing_support import GENERATION_NODE_TYPES

    assert GenerateCanonicalContentNode.type == "generate_canonical_content"
    assert GenerateTextNode.type == "generate_text"
    assert GenerateCanonicalContentNode.type != GenerateTextNode.type
    source = inspect.getsource(GenerateCanonicalContentNode.execute)
    assert "ContentGenerationService" in source
    assert "get_llm_provider" not in source
    assert hasattr(canonical_mod, "extract_canonical_text")
    assert "generate_canonical_content" in GENERATION_NODE_TYPES


@pytest.mark.workflow_production_gap
def test_node_implementation_status_and_compiler_gate() -> None:
    from backend.modules.workflows.compiler_semantics import validate_node_executability
    from backend.modules.workflows.nodes.base import NodeImplementationStatus, make_stub_node
    from backend.modules.workflows.nodes.research import ResearchSourcesNode
    from backend.modules.workflows.nodes.analytics import FetchMetricsNode
    from backend.modules.workflows.registry import build_default_registry

    assert hasattr(ResearchSourcesNode, "implementation_status")
    assert ResearchSourcesNode.implementation_status == NodeImplementationStatus.STABLE
    assert FetchMetricsNode.implementation_status == NodeImplementationStatus.STABLE
    stub = make_stub_node(
        node_type="tmp_unavailable",
        category="test",
        display_name="Tmp",
        description="tmp",
    )
    assert stub.implementation_status == NodeImplementationStatus.UNAVAILABLE
    assert stub.is_executable() is False
    assert callable(validate_node_executability)
    defs = {d.type: d for d in build_default_registry().list_definitions()}
    assert defs["schedule_trigger"].executable is False
    assert defs["research_sources"].executable is True


@pytest.mark.workflow_production_gap
def test_node_definitions_expose_config_schema_for_editor() -> None:
    from backend.modules.workflows.registry import build_default_registry

    defs = {d.type: d for d in build_default_registry().list_definitions()}
    gen = defs["generate_text"]
    assert isinstance(gen.config_schema, dict)
    assert "properties" in gen.config_schema
    assert gen.input_ports
    assert any(p.name == "prompt" for p in gen.input_ports)


def test_workflow_production_gap_suite_is_manifested() -> None:
    """Non-xfail guard: gap module must stay in the regression manifest."""
    from backend.tests import test_regression_manifest as manifest

    assert "test_workflow_production_gaps.py" in manifest.REGRESSION_MANIFEST.get(
        "workflow_production_gaps", ()
    )
