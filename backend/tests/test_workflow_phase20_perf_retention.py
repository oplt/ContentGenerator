"""Phase 20 — performance indexes + historical payload retention."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Table, event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.core.config import settings
from backend.db.base import Base
from backend.modules.approvals.models import WebhookInbox
from backend.modules.audit.models import AuditLog
from backend.modules.content_strategy.models import Brand
from backend.modules.identity_access.models import Tenant
from backend.modules.operations.models import TaskExecution
from backend.modules.publishing.models import SocialAccount
from backend.modules.workflows.models import Automation, WorkflowDefinition, WorkflowVersion
from backend.modules.workflows.retention import (
    _is_already_scrubbed,
    run_workflow_retention,
)
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
)
from backend.workers.celery_app import celery_app


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_head_is_phase20() -> None:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == ["d2e3f4a5b6c7"]


def test_phase20_migration_defines_hot_path_indexes() -> None:
    path = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "d2e3f4a5b6c7_phase20_perf_retention_indexes.py"
    )
    body = path.read_text(encoding="utf-8")
    for name in (
        "ix_workflow_node_runs_ready_run_created_at",
        "ix_workflow_node_runs_expired_claims",
        "ix_workflow_node_runs_finished_at_terminal",
        "ix_workflow_waits_pending_wake_at",
        "ix_workflow_runs_tenant_status_created_at",
        "ix_publishing_jobs_tenant_social_account_created_at",
        "ix_publishing_jobs_approval_request_id",
        "ix_approval_requests_pending_expires_at",
        "ix_task_executions_created_at",
        "ix_webhooks_inbox_status_received_at",
    ):
        assert name in body


def test_retention_beat_and_route_registered() -> None:
    assert "workflow-retention-hourly" in celery_app.conf.beat_schedule
    entry = celery_app.conf.beat_schedule["workflow-retention-hourly"]
    assert entry["task"] == "backend.workers.tasks.run_workflow_retention_task"
    routes = celery_app.conf.task_routes
    assert "backend.workers.tasks.run_workflow_retention_task" in routes


async def _session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk(dbapi_conn, _):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE users (id CHAR(32) NOT NULL PRIMARY KEY)"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=cast(list[Table], [
                    Tenant.__table__,
                    Brand.__table__,
                    SocialAccount.__table__,
                    WorkflowDefinition.__table__,
                    WorkflowVersion.__table__,
                    Automation.__table__,
                    WorkflowRun.__table__,
                    WorkflowNodeRun.__table__,
                    TaskExecution.__table__,
                    WebhookInbox.__table__,
                    AuditLog.__table__,
                ]),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False)()


async def _seed_retention_rows(db: AsyncSession) -> dict[str, uuid.UUID]:
    tenant = Tenant(name="Ret", slug=f"ret-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    await db.flush()
    definition = WorkflowDefinition(
        tenant_id=tenant.id, name="W", slug=f"w-{uuid.uuid4().hex[:8]}"
    )
    db.add(definition)
    await db.flush()
    version = WorkflowVersion(
        tenant_id=tenant.id,
        workflow_definition_id=definition.id,
        version=1,
        graph_json={"nodes": [], "edges": []},
        published_at=datetime.now(timezone.utc),
    )
    db.add(version)
    await db.flush()

    old = datetime.now(timezone.utc) - timedelta(days=60)
    recent = datetime.now(timezone.utc) - timedelta(hours=1)

    run = WorkflowRun(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        workflow_definition_id=definition.id,
        workflow_version_id=version.id,
        trigger_type="manual",
        trigger_payload={},
        status=WorkflowRunStatus.SUCCEEDED.value,
        context_snapshot={},
        started_at=old,
        finished_at=old,
    )
    db.add(run)
    await db.flush()

    old_node = WorkflowNodeRun(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        workflow_run_id=run.id,
        node_id="n1",
        node_type="generate_text",
        node_version=1,
        status=WorkflowNodeRunStatus.SUCCEEDED.value,
        attempt=1,
        iteration_key="",
        input_json={"prompt": "keep-me-out"},
        output_json={"text": "large-body"},
        error_json=None,
        task_execution_ids=[],
        started_at=old,
        finished_at=old,
        cancellation_requested=False,
    )
    recent_node = WorkflowNodeRun(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        workflow_run_id=run.id,
        node_id="n2",
        node_type="generate_text",
        node_version=1,
        status=WorkflowNodeRunStatus.SUCCEEDED.value,
        attempt=1,
        iteration_key="",
        input_json={"prompt": "fresh"},
        output_json={"text": "fresh"},
        error_json=None,
        task_execution_ids=[],
        started_at=recent,
        finished_at=recent,
        cancellation_requested=False,
    )
    db.add_all([old_node, recent_node])

    old_task = TaskExecution(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        task_name="old",
        queue_name="generation",
        status="completed",
        progress=100,
        attempt=1,
        payload={"x": 1},
        result={"y": 2},
        finished_at=old,
    )
    old_task.created_at = old
    recent_task = TaskExecution(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        task_name="new",
        queue_name="generation",
        status="completed",
        progress=100,
        attempt=1,
        payload={"x": 1},
        result={"y": 2},
        finished_at=recent,
    )
    recent_task.created_at = recent
    db.add_all([old_task, recent_task])

    old_hook = WebhookInbox(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        provider="workflow",
        event_type="x",
        dedupe_key=f"d-{uuid.uuid4().hex}",
        payload={"secret": "body"},
        received_at=old,
        processed_at=old,
        signature_valid=True,
        status="processed",
    )
    recent_hook = WebhookInbox(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        provider="workflow",
        event_type="x",
        dedupe_key=f"d-{uuid.uuid4().hex}",
        payload={"secret": "fresh"},
        received_at=recent,
        processed_at=recent,
        signature_valid=True,
        status="processed",
    )
    db.add_all([old_hook, recent_hook])

    audit = AuditLog(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        actor_user_id=None,
        action="workflow.run.started",
        entity_type="workflow_run",
        entity_id=str(run.id),
        correlation_id="ret-test",
        severity="info",
        message="run started",
        payload={"ok": True},
    )
    audit.created_at = old
    db.add(audit)
    await db.commit()

    return {
        "tenant_id": tenant.id,
        "old_node_id": old_node.id,
        "recent_node_id": recent_node.id,
        "old_task_id": old_task.id,
        "recent_task_id": recent_task.id,
        "old_hook_id": old_hook.id,
        "recent_hook_id": recent_hook.id,
        "audit_id": audit.id,
    }


def test_retention_scrubs_payloads_deletes_tasks_preserves_audit(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "WORKFLOW_RETENTION_ENABLED", True)
    monkeypatch.setattr(settings, "WORKFLOW_RETENTION_NODE_PAYLOAD_DAYS", 30)
    monkeypatch.setattr(settings, "WORKFLOW_RETENTION_TASK_EXECUTION_DAYS", 14)
    monkeypatch.setattr(settings, "WORKFLOW_RETENTION_WEBHOOK_PAYLOAD_DAYS", 14)
    monkeypatch.setattr(settings, "WORKFLOW_RETENTION_ARCHIVE_TO_STORAGE", False)

    async def exercise() -> None:
        db = await _session()
        ids = await _seed_retention_rows(db)
        summary = await run_workflow_retention(db)
        await db.commit()

        assert summary["nodes_scrubbed"] == 1
        assert summary["task_executions_deleted"] == 1
        assert summary["webhooks_scrubbed"] == 1

        old_node = await db.get(WorkflowNodeRun, ids["old_node_id"])
        recent_node = await db.get(WorkflowNodeRun, ids["recent_node_id"])
        assert old_node is not None and recent_node is not None
        assert _is_already_scrubbed(old_node.input_json)
        assert _is_already_scrubbed(old_node.output_json)
        assert recent_node.input_json == {"prompt": "fresh"}

        assert await db.get(TaskExecution, ids["old_task_id"]) is None
        assert await db.get(TaskExecution, ids["recent_task_id"]) is not None

        old_hook = await db.get(WebhookInbox, ids["old_hook_id"])
        recent_hook = await db.get(WebhookInbox, ids["recent_hook_id"])
        assert old_hook is not None and _is_already_scrubbed(old_hook.payload)
        assert recent_hook is not None and recent_hook.payload == {"secret": "fresh"}

        audit = await db.get(AuditLog, ids["audit_id"])
        assert audit is not None
        assert audit.payload == {"ok": True}

        # Idempotent second pass
        summary2 = await run_workflow_retention(db)
        await db.commit()
        assert summary2["nodes_scrubbed"] == 0
        assert summary2["task_executions_deleted"] == 0
        assert summary2["webhooks_scrubbed"] == 0

        await db.close()

    asyncio.run(exercise())


def test_retention_disabled_is_noop(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WORKFLOW_RETENTION_ENABLED", False)

    async def exercise() -> None:
        db = await _session()
        await _seed_retention_rows(db)
        summary = await run_workflow_retention(db)
        assert summary == {
            "enabled": False,
            "nodes_scrubbed": 0,
            "task_executions_deleted": 0,
            "webhooks_scrubbed": 0,
        }
        rows = (await db.execute(select(TaskExecution))).scalars().all()
        assert len(rows) == 2
        await db.close()

    asyncio.run(exercise())
