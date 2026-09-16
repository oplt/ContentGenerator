"""Phase 3 — workflow graph schema + compiler + version publish."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import cast

import pytest
from sqlalchemy import Table, create_engine, event, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from backend.db.base import Base
from backend.modules.identity_access.models import Tenant
from backend.modules.workflows.compiler import WorkflowCompiler
from backend.modules.workflows.graph_schema import CompileContext, WorkflowGraph
from backend.modules.workflows.models import WorkflowDefinition, WorkflowVersion
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.repository import WorkflowRepository
from backend.modules.workflows.versioning import WorkflowVersioningService


@pytest.fixture(autouse=True)
def _fresh_registry() -> Iterator[None]:
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


def _linear_slice_graph() -> dict:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {
                "id": "generate",
                "type": "generate_text",
                "version": 1,
                "config": {"max_tokens": 200},
            },
            {"id": "approval", "type": "approval", "version": 1, "config": {}},
            {"id": "publish", "type": "publish", "version": 1, "config": {"dry_run": True}},
        ],
        "edges": [
            {"source": "trigger", "target": "generate"},
            {"source": "generate", "target": "approval"},
            {"source": "approval", "target": "publish", "condition": "approved"},
        ],
    }


def _compile_ctx() -> CompileContext:
    account_id = uuid.uuid4()
    return CompileContext(
        social_account_ids=[account_id],
        account_capabilities={str(account_id): ["llm", "publish"]},
    )


def test_valid_linear_graph_compiles() -> None:
    result = WorkflowCompiler().validate_graph(_linear_slice_graph(), _compile_ctx())
    assert result.valid is True
    assert result.checksum
    assert result.normalized_graph is not None


def test_duplicate_node_ids_rejected() -> None:
    graph = _linear_slice_graph()
    graph["nodes"].append({"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}})
    result = WorkflowCompiler().validate_graph(graph, _compile_ctx())
    assert result.valid is False
    assert any(e.code == "duplicate_node_id" for e in result.errors)


def test_dangling_edge_rejected() -> None:
    graph = _linear_slice_graph()
    graph["edges"].append({"source": "publish", "target": "missing"})
    result = WorkflowCompiler().validate_graph(graph, _compile_ctx())
    assert result.valid is False
    assert any(e.code == "dangling_edge_target" for e in result.errors)


def test_cycle_rejected() -> None:
    graph = _linear_slice_graph()
    graph["edges"].append({"source": "publish", "target": "generate"})
    result = WorkflowCompiler().validate_graph(graph, _compile_ctx())
    assert result.valid is False
    assert any(e.code == "cycle_detected" for e in result.errors)


def test_unreachable_node_rejected() -> None:
    graph = _linear_slice_graph()
    graph["nodes"].append({"id": "orphan", "type": "summarize", "version": 1, "config": {}})
    result = WorkflowCompiler().validate_graph(graph, _compile_ctx())
    assert result.valid is False
    assert any(e.code == "unreachable_node" and e.node_id == "orphan" for e in result.errors)


def test_multiple_triggers_rejected() -> None:
    graph = _linear_slice_graph()
    graph["nodes"].append(
        {"id": "trigger2", "type": "schedule_trigger", "version": 1, "config": {}}
    )
    result = WorkflowCompiler().validate_graph(graph, _compile_ctx())
    assert result.valid is False
    assert any(e.code == "multiple_triggers" for e in result.errors)


def test_missing_publish_targets_rejected() -> None:
    result = WorkflowCompiler().validate_graph(
        _linear_slice_graph(), CompileContext(require_publish_targets=True)
    )
    assert result.valid is False
    assert any(e.code == "missing_publish_targets" for e in result.errors)


def test_approval_after_publish_rejected() -> None:
    graph = {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {"id": "publish", "type": "publish", "version": 1, "config": {}},
            {"id": "approval", "type": "approval", "version": 1, "config": {}},
        ],
        "edges": [
            {"source": "trigger", "target": "publish"},
            {"source": "publish", "target": "approval"},
        ],
    }
    result = WorkflowCompiler().validate_graph(graph, _compile_ctx())
    assert result.valid is False
    assert any(e.code == "approval_after_publish" for e in result.errors)


def test_incompatible_capabilities_rejected() -> None:
    account_id = uuid.uuid4()
    ctx = CompileContext(
        social_account_ids=[account_id],
        account_capabilities={str(account_id): ["publish"]},
    )
    result = WorkflowCompiler().validate_graph(_linear_slice_graph(), ctx)
    assert result.valid is False
    assert any(e.code == "incompatible_capabilities" for e in result.errors)


def test_canonical_graph_schema_roundtrip() -> None:
    parsed = WorkflowGraph.model_validate(_linear_slice_graph())
    assert len(parsed.nodes) == 4
    assert parsed.edges[2].condition == "approved"


def test_versioning_service_validate_graph_helper() -> None:
    service = WorkflowVersioningService.__new__(WorkflowVersioningService)
    service.compiler = WorkflowCompiler()
    result = service.validate_graph(
        {"nodes": [{"id": "t", "type": "manual_trigger", "version": 1, "config": {}}]},
        CompileContext(),
    )
    assert result.valid is True


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id CHAR(32) NOT NULL PRIMARY KEY)"))
    Base.metadata.create_all(
        engine,
        tables=cast(
            list[Table],
            [Tenant.__table__, WorkflowDefinition.__table__, WorkflowVersion.__table__],
        ),
    )
    return sessionmaker(engine, expire_on_commit=False)()


def test_publish_marks_version_immutable_and_new_draft_version() -> None:
    db = _session()
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    db.flush()

    definition = WorkflowDefinition(
        tenant_id=tenant.id,
        name="Daily",
        slug="daily",
        status="draft",
    )
    db.add(definition)
    db.flush()

    repo = WorkflowRepository(db)
    v1 = WorkflowVersion(
        tenant_id=tenant.id,
        workflow_definition_id=definition.id,
        version=1,
        graph_json=_linear_slice_graph(),
    )
    db.add(v1)
    db.flush()

    compiled = WorkflowCompiler().validate_graph(v1.graph_json, _compile_ctx())
    assert compiled.valid and compiled.checksum
    repo.mark_published(v1, checksum=compiled.checksum)
    definition.current_version_id = v1.id
    definition.status = "active"
    db.commit()

    with pytest.raises(PermissionError):
        repo.assert_mutable(v1)

    current = db.execute(
        select(func.max(WorkflowVersion.version)).where(
            WorkflowVersion.workflow_definition_id == definition.id
        )
    ).scalar_one()
    assert int(current) == 1

    v2 = WorkflowVersion(
        tenant_id=tenant.id,
        workflow_definition_id=definition.id,
        version=2,
        graph_json=_linear_slice_graph(),
    )
    db.add(v2)
    db.commit()
    assert v2.published_at is None
    assert v1.published_at is not None
    assert v1.checksum == compiled.checksum
    db.close()
