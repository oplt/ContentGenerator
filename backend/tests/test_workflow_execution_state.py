"""Phase 4 — WorkflowRun / WorkflowNodeRun durable execution state."""

from __future__ import annotations

import uuid
from typing import cast

import pytest
from sqlalchemy import Table, create_engine, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.db.base import Base
from backend.modules.identity_access.models import Tenant
from backend.modules.operations.models import TaskExecution
from backend.modules.workflows.models import WorkflowDefinition, WorkflowVersion
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id CHAR(32) NOT NULL PRIMARY KEY)"))
        # Composite FK targets referenced even when brand_id/automation_id are NULL.
        conn.execute(
            text(
                "CREATE TABLE brands ("
                "id CHAR(32) NOT NULL, tenant_id CHAR(32) NOT NULL, "
                "PRIMARY KEY (id), UNIQUE (tenant_id, id))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE automations ("
                "id CHAR(32) NOT NULL, tenant_id CHAR(32) NOT NULL, "
                "PRIMARY KEY (id), UNIQUE (tenant_id, id))"
            )
        )
    Base.metadata.create_all(
        engine,
        tables=cast(
            list[Table],
            [
                Tenant.__table__,
                WorkflowDefinition.__table__,
                WorkflowVersion.__table__,
                TaskExecution.__table__,
                WorkflowRun.__table__,
                WorkflowNodeRun.__table__,
            ],
        ),
    )
    return sessionmaker(engine, expire_on_commit=False)()


def _seed_definition(db: Session, tenant_id: uuid.UUID) -> tuple[WorkflowDefinition, WorkflowVersion]:
    definition = WorkflowDefinition(
        tenant_id=tenant_id,
        name="Slice",
        slug=f"slice-{uuid.uuid4().hex[:8]}",
        status="active",
    )
    db.add(definition)
    db.flush()
    version = WorkflowVersion(
        tenant_id=tenant_id,
        workflow_definition_id=definition.id,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    db.add(version)
    db.flush()
    definition.current_version_id = version.id
    db.flush()
    return definition, version


def test_workflow_run_and_node_runs_persist_with_task_link() -> None:
    db = _session()
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    db.flush()
    definition, version = _seed_definition(db, tenant.id)

    task = TaskExecution(
        tenant_id=tenant.id,
        task_name="backend.workers.tasks.run_workflow_node",
        queue_name="default",
        status="queued",
        correlation_id="corr-1",
    )
    db.add(task)
    db.flush()

    run = WorkflowRun(
        tenant_id=tenant.id,
        workflow_definition_id=definition.id,
        workflow_version_id=version.id,
        trigger_type="manual",
        trigger_payload={"source": "api"},
        status=WorkflowRunStatus.RUNNING.value,
        context_snapshot={"accounts": []},
        correlation_id="corr-1",
    )
    db.add(run)
    db.flush()

    node = WorkflowNodeRun(
        tenant_id=tenant.id,
        workflow_run_id=run.id,
        node_id="generate",
        node_type="generate_text",
        node_version=1,
        status=WorkflowNodeRunStatus.RUNNING.value,
        attempt=1,
        input_json={"prompt": "hi"},
        task_execution_id=task.id,
        task_execution_ids=[str(task.id)],
    )
    db.add(node)
    db.commit()

    loaded = db.get(WorkflowRun, run.id)
    assert loaded is not None
    assert loaded.status == WorkflowRunStatus.RUNNING.value
    assert loaded.correlation_id == "corr-1"

    nodes = (
        db.execute(select(WorkflowNodeRun).where(WorkflowNodeRun.workflow_run_id == run.id))
        .scalars()
        .all()
    )
    assert len(nodes) == 1
    assert nodes[0].task_execution_id == task.id
    assert nodes[0].task_execution_ids == [str(task.id)]
    db.close()


def test_workflow_run_tenant_isolation() -> None:
    db = _session()
    t1 = Tenant(name="A", slug=f"a-{uuid.uuid4().hex[:8]}")
    t2 = Tenant(name="B", slug=f"b-{uuid.uuid4().hex[:8]}")
    db.add_all([t1, t2])
    db.flush()
    d1, v1 = _seed_definition(db, t1.id)
    d2, v2 = _seed_definition(db, t2.id)

    run1 = WorkflowRun(
        tenant_id=t1.id,
        workflow_definition_id=d1.id,
        workflow_version_id=v1.id,
        status=WorkflowRunStatus.QUEUED.value,
    )
    run2 = WorkflowRun(
        tenant_id=t2.id,
        workflow_definition_id=d2.id,
        workflow_version_id=v2.id,
        status=WorkflowRunStatus.QUEUED.value,
    )
    db.add_all([run1, run2])
    db.commit()

    listed = (
        db.execute(select(WorkflowRun).where(WorkflowRun.tenant_id == t1.id)).scalars().all()
    )
    assert len(listed) == 1
    assert listed[0].id == run1.id
    cross = db.execute(
        select(WorkflowRun).where(WorkflowRun.id == run2.id, WorkflowRun.tenant_id == t1.id)
    ).scalar_one_or_none()
    assert cross is None
    db.close()


def test_duplicate_node_id_per_run_rejected() -> None:
    db = _session()
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    db.flush()
    definition, version = _seed_definition(db, tenant.id)
    run = WorkflowRun(
        tenant_id=tenant.id,
        workflow_definition_id=definition.id,
        workflow_version_id=version.id,
    )
    db.add(run)
    db.flush()
    db.add(
        WorkflowNodeRun(
            tenant_id=tenant.id,
            workflow_run_id=run.id,
            node_id="trigger",
            node_type="manual_trigger",
        )
    )
    db.commit()
    db.add(
        WorkflowNodeRun(
            tenant_id=tenant.id,
            workflow_run_id=run.id,
            node_id="trigger",
            node_type="manual_trigger",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.close()


def test_cross_tenant_run_definition_rejected() -> None:
    db = _session()
    t1 = Tenant(name="A", slug=f"a-{uuid.uuid4().hex[:8]}")
    t2 = Tenant(name="B", slug=f"b-{uuid.uuid4().hex[:8]}")
    db.add_all([t1, t2])
    db.flush()
    _d1, _v1 = _seed_definition(db, t1.id)
    d2, v2 = _seed_definition(db, t2.id)

    db.add(
        WorkflowRun(
            tenant_id=t1.id,
            workflow_definition_id=d2.id,
            workflow_version_id=v2.id,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.close()
