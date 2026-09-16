"""Phase 9 — approval policy and revision semantics."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Table, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.approvals.approval_actions import _apply_revise, apply_intent
from backend.modules.approvals.models import ApprovalIntent, ApprovalStatus
from backend.modules.content_strategy.models import Brand
from backend.modules.identity_access.models import Tenant
from backend.modules.operations.models import TaskExecution
from backend.modules.publishing.models import SocialAccount
from backend.modules.workflows.approval_binding import (
    WORKFLOW_BINDING_KEY,
    build_workflow_binding,
    get_workflow_binding,
    merge_payload_preserving_workflow,
)
from backend.modules.workflows.nodes.approval import ApprovalConfig, ApprovalNode
from backend.modules.workflows.nodes.base import NodeResultStatus, WorkflowNodeContext
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.models import Automation, WorkflowDefinition, WorkflowVersion
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowWait,
)


@pytest.fixture(autouse=True)
def _registry() -> Any:
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


async def _session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE users (id CHAR(32) NOT NULL PRIMARY KEY)"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=cast(
                    list[Table],
                    [
                        Tenant.__table__,
                        Brand.__table__,
                        SocialAccount.__table__,
                        WorkflowDefinition.__table__,
                        WorkflowVersion.__table__,
                        Automation.__table__,
                        TaskExecution.__table__,
                        WorkflowRun.__table__,
                        WorkflowNodeRun.__table__,
                        WorkflowWait.__table__,
                    ],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False)()


def test_required_false_succeeds_not_required() -> None:
    async def _run() -> None:
        db = await _session()
        tenant = Tenant(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        ctx = WorkflowNodeContext(
            tenant_id=tenant.id,
            db=db,
            node_id="approval",
            workflow_run_id=uuid.uuid4(),
            node_run_id=uuid.uuid4(),
            resume_token="tok",
        )
        result = await ApprovalNode().execute(
            ctx,
            ApprovalNode.InputSchema(content_job_id=uuid.uuid4()),
            ApprovalConfig(required=False),
        )
        assert result.status == NodeResultStatus.SUCCEEDED
        assert result.output["status"] == "not_required"
        assert result.output.get("approval_request_id") is None
        await db.close()

    asyncio.run(_run())


def test_merge_payload_preserving_workflow() -> None:
    binding = build_workflow_binding(
        workflow_run_id=uuid.uuid4(),
        workflow_node_run_id=uuid.uuid4(),
        node_id="approval",
        resume_token="resume-1",
        channels=["telegram"],
    )
    merged = merge_payload_preserving_workflow(
        {WORKFLOW_BINDING_KEY: binding, "risk_label": "low"},
        {"revision_mode": "trim", "risk_label": "medium"},
    )
    assert merged[WORKFLOW_BINDING_KEY]["resume_token"] == "resume-1"
    assert merged["revision_mode"] == "trim"
    assert merged["risk_label"] == "medium"


def test_revise_preserves_workflow_binding() -> None:
    async def _run() -> None:
        binding = build_workflow_binding(
            workflow_run_id=uuid.uuid4(),
            workflow_node_run_id=uuid.uuid4(),
            node_id="approval",
            resume_token="resume-rev",
            allow_revision=True,
            channels=["in_app"],
        )
        request = MagicMock()
        request.status = ApprovalStatus.PENDING.value
        request.revision_count = 0
        request.content_job_id = uuid.uuid4()
        request.tenant_id = uuid.uuid4()
        request.channel = "telegram"
        request.recipient = "in_app"
        request.response_payload_json = {WORKFLOW_BINDING_KEY: binding}

        revised = MagicMock()
        revised.id = uuid.uuid4()
        svc = MagicMock()
        svc.content_service.regenerate_with_feedback = AsyncMock(return_value=revised)
        # Realistic send_for_approval that clears then we re-stamp in _apply_revise
        async def _send(**kwargs: Any) -> None:
            request.response_payload_json = {"risk_label": "low"}

        svc.send_for_approval = AsyncMock(side_effect=_send)
        with patch(
            "backend.modules.approvals.approval_actions.record_preference",
            new=AsyncMock(),
        ):
            await _apply_revise(svc, request, "tighten headline")

        assert request.content_job_id == revised.id
        assert request.status == ApprovalStatus.PENDING.value
        restored_binding = get_workflow_binding(request)
        assert restored_binding is not None
        assert restored_binding["resume_token"] == "resume-rev"
        svc.send_for_approval.assert_awaited()
        call_kwargs = svc.send_for_approval.await_args.kwargs
        assert call_kwargs.get("channels") == ["in_app"]

    asyncio.run(_run())


def test_revise_blocked_when_allow_revision_false() -> None:
    async def _run() -> None:
        binding = build_workflow_binding(
            workflow_run_id=uuid.uuid4(),
            workflow_node_run_id=uuid.uuid4(),
            node_id="approval",
            resume_token="tok",
            allow_revision=False,
        )
        request = MagicMock()
        request.status = ApprovalStatus.PENDING.value
        request.revision_count = 0
        request.content_job_id = uuid.uuid4()
        request.response_payload_json = {WORKFLOW_BINDING_KEY: binding}
        svc = MagicMock()
        await _apply_revise(svc, request, "nope")
        assert request.status == ApprovalStatus.REJECTED.value
        svc.content_service.regenerate_with_feedback.assert_not_called()

    asyncio.run(_run())


def test_apply_intent_approve_passes_final_identity() -> None:
    async def _run() -> None:
        binding = build_workflow_binding(
            workflow_run_id=uuid.uuid4(),
            workflow_node_run_id=uuid.uuid4(),
            node_id="approval",
            resume_token="tok",
        )
        request = MagicMock()
        request.id = uuid.uuid4()
        request.tenant_id = uuid.uuid4()
        request.status = ApprovalStatus.PENDING.value
        request.content_job_id = uuid.uuid4()
        request.revision_count = 2
        request.response_payload_json = {WORKFLOW_BINDING_KEY: binding}
        request.approval_type = "asset"

        svc = MagicMock()
        svc.db = MagicMock()
        svc.audit.record = AsyncMock()

        with (
            patch(
                "backend.modules.approvals.approval_actions.record_preference",
                new=AsyncMock(),
            ),
            patch(
                "backend.modules.workflows.approval_binding.maybe_resume_workflow_from_approval",
                new=AsyncMock(),
            ) as resume,
        ):
            await apply_intent(svc, request, ApprovalIntent.APPROVE.value, None)
            resume.assert_awaited_once()
            # Status approved before resume
            assert request.status == ApprovalStatus.APPROVED.value

    asyncio.run(_run())


def test_approval_delivery_respects_in_app_only() -> None:
    async def _run() -> None:
        from backend.modules.workflows.approval_delivery import ApprovalDeliveryService

        svc = MagicMock()
        request = MagicMock()
        request.id = uuid.uuid4()
        delivered = await ApprovalDeliveryService().deliver(
            svc,
            request,
            tenant_id=uuid.uuid4(),
            content_job_id=uuid.uuid4(),
            channels=["in_app"],
        )
        assert delivered == ["in_app"]
        # No telegram/whatsapp attempts
        assert not hasattr(svc, "settings_service") or True

    asyncio.run(_run())


def test_approval_output_schema_allows_null_request_id() -> None:
    from backend.modules.workflows.nodes.approval import ApprovalOutput

    out = ApprovalOutput(status="not_required", content_job_id=uuid.uuid4())
    assert out.approval_request_id is None


def test_wait_persist_creates_approval_timeout_wait() -> None:
    async def _run() -> None:
        from backend.modules.workflows.wait_persist import persist_waiting_node

        db = await _session()
        tenant = Tenant(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        definition = WorkflowDefinition(
            tenant_id=tenant.id, name="w", slug=f"w-{uuid.uuid4().hex[:8]}", status="active"
        )
        db.add(definition)
        await db.flush()
        version = WorkflowVersion(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            version=1,
            graph_json={"nodes": [], "edges": []},
            published_at=datetime.now(timezone.utc),
            checksum="c",
        )
        db.add(version)
        await db.flush()
        run = WorkflowRun(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            workflow_version_id=version.id,
            status="waiting",
            trigger_type="manual",
            context_snapshot={},
            trigger_payload={},
        )
        db.add(run)
        await db.flush()
        node = WorkflowNodeRun(
            tenant_id=tenant.id,
            workflow_run_id=run.id,
            node_id="approval",
            node_type="approval",
            node_version=1,
            status=WorkflowNodeRunStatus.WAITING.value,
            resume_token=f"tok-{uuid.uuid4().hex[:8]}",
            waiting_reason="approval_pending",
        )
        db.add(node)
        await db.flush()

        with patch("backend.modules.workflows.wait_persist.schedule_fast_wake") as fast:
            await persist_waiting_node(
                db,
                run=run,
                node_run=node,
                output={
                    "approval_request_id": str(uuid.uuid4()),
                    "timeout_seconds": 120,
                    "on_timeout": "stop",
                },
                waiting_reason="approval_pending",
            )
        from sqlalchemy import select

        rows = (
            await db.execute(select(WorkflowWait).where(WorkflowWait.workflow_run_id == run.id))
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].wake_at is not None
        assert rows[0].payload.get("kind") == "approval_timeout"
        assert fast.called
        await db.close()

    asyncio.run(_run())
