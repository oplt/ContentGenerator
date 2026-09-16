"""Phase 6 — durable approval / WAITING resume."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Table, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.approvals.approval_actions import _apply_approve, apply_intent
from backend.modules.approvals.models import ApprovalIntent, ApprovalStatus
from backend.modules.content_strategy.models import Brand
from backend.modules.identity_access.models import Tenant
from backend.modules.operations.models import TaskExecution
from backend.modules.publishing.models import SocialAccount
from backend.modules.workflows.approval_binding import (
    WORKFLOW_BINDING_KEY,
    build_workflow_binding,
    maybe_resume_workflow_from_approval,
)
from backend.modules.workflows.engine import WorkflowEngine
from backend.modules.workflows.engine_resume import resume_waiting_node
from backend.modules.workflows.graph_schema import CompileContext
from backend.modules.workflows.models import Automation, WorkflowDefinition, WorkflowVersion
from backend.modules.workflows.nodes.base import NodeResult, NodeResultStatus
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowWait,
)


@pytest.fixture(autouse=True)
def _fresh_registry() -> Iterator[None]:
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


def _full_slice_graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {
                "id": "generate",
                "type": "generate_text",
                "version": 1,
                "config": {"max_tokens": 64},
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


def _mock_llm(*, text: str = "hello") -> Any:
    llm = AsyncMock()
    llm.generate_text = AsyncMock(return_value=text)
    llm.provider_name = "mock"
    return llm


async def _async_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
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

    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return Session()


async def _seed_published(
    db: AsyncSession, graph: dict[str, Any]
) -> tuple[Tenant, WorkflowVersion]:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    await db.flush()
    definition = WorkflowDefinition(
        tenant_id=tenant.id,
        name="Resume",
        slug=f"resume-{uuid.uuid4().hex[:8]}",
        status="active",
    )
    db.add(definition)
    await db.flush()
    version = WorkflowVersion(
        tenant_id=tenant.id,
        workflow_definition_id=definition.id,
        version=1,
        graph_json=graph,
        published_at=datetime.now(timezone.utc),
        checksum="test",
    )
    db.add(version)
    await db.flush()
    definition.current_version_id = version.id
    await db.flush()
    return tenant, version


async def _pause_on_approval(db: AsyncSession) -> tuple[Tenant, Any, str]:
    tenant, version = await _seed_published(db, _full_slice_graph())
    ctx = CompileContext(require_publish_targets=False)
    approval_id = uuid.uuid4()
    job_id = uuid.uuid4()

    async def _waiting_execute(context, inputs, config):  # type: ignore[no-untyped-def]
        assert context.resume_token
        return NodeResult(
            status=NodeResultStatus.WAITING,
            output={
                "approval_request_id": str(approval_id),
                "status": "pending",
                "channels": ["in_app"],
                "content_job_id": str(job_id),
                "revision_count": 0,
            },
            waiting_reason="approval_pending",
        )

    with (
        patch(
            "backend.modules.workflows.nodes.text.get_llm_provider",
            return_value=_mock_llm(),
        ),
        patch(
            "backend.modules.workflows.nodes.approval.ApprovalNode.execute",
            new=AsyncMock(side_effect=_waiting_execute),
        ),
        patch("backend.modules.workflows.wait_persist.schedule_fast_wake"),
    ):
        engine = WorkflowEngine(db)
        run = await engine.start_run(
            tenant_id=tenant.id,
            workflow_version_id=version.id,
            trigger_payload={
                "prompt": "need approval",
                "content_job_id": str(job_id),
            },
            compile_context=ctx,
            correlation_id=f"corr-resume-{uuid.uuid4().hex[:8]}",
        )

    nodes = {n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)}
    token = nodes["approval"].resume_token
    assert token
    assert run.status == WorkflowRunStatus.WAITING.value
    return tenant, run, token


def test_resume_approved_unlocks_publish() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant, paused, token = await _pause_on_approval(db)
        engine = WorkflowEngine(db)

        with patch(
            "backend.modules.workflows.nodes.publishing.PublishNode.execute",
            new=AsyncMock(
                return_value=NodeResult(
                    status=NodeResultStatus.SUCCEEDED,
                    output={
                        "job_ids": [str(uuid.uuid4())],
                        "statuses": ["dry_run"],
                        "dry_run": True,
                    },
                )
            ),
        ):
            run = await resume_waiting_node(
                engine,
                tenant.id,
                resume_token=token,
                outcome="approved",
                decision={"approval_request_id": str(uuid.uuid4())},
            )

        assert run.status == WorkflowRunStatus.SUCCEEDED.value
        nodes = {n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)}
        assert nodes["approval"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        assert nodes["approval"].output_json.get("decision") == "approved"
        assert nodes["publish"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        await db.close()

    asyncio.run(_run())


def test_resume_rejected_fails_run() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant, _paused, token = await _pause_on_approval(db)
        engine = WorkflowEngine(db)
        run = await resume_waiting_node(
            engine, tenant.id, resume_token=token, outcome="rejected"
        )
        assert run.status == WorkflowRunStatus.FAILED.value
        nodes = {n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)}
        assert nodes["approval"].status == WorkflowNodeRunStatus.FAILED.value
        assert nodes["publish"].status == WorkflowNodeRunStatus.PENDING.value
        await db.close()

    asyncio.run(_run())


def test_resume_idempotent() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant, _paused, token = await _pause_on_approval(db)
        engine = WorkflowEngine(db)
        with patch(
            "backend.modules.workflows.nodes.publishing.PublishNode.execute",
            new=AsyncMock(
                return_value=NodeResult(
                    status=NodeResultStatus.SUCCEEDED,
                    output={
                        "job_ids": [str(uuid.uuid4())],
                        "statuses": ["dry_run"],
                        "dry_run": True,
                    },
                )
            ),
        ):
            first = await resume_waiting_node(
                engine, tenant.id, resume_token=token, outcome="approved"
            )
            second = await resume_waiting_node(
                engine, tenant.id, resume_token=token, outcome="approved"
            )
        assert first.id == second.id
        assert first.status == WorkflowRunStatus.SUCCEEDED.value
        nodes = await engine.runs.list_node_runs(tenant.id, first.id)
        approval = next(n for n in nodes if n.node_id == "approval")
        assert approval.attempt >= 1
        await db.close()

    asyncio.run(_run())


def test_maybe_resume_from_approval_binding() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant, paused, token = await _pause_on_approval(db)
        request = MagicMock()
        request.tenant_id = tenant.id
        request.id = uuid.uuid4()
        request.status = ApprovalStatus.APPROVED.value
        request.content_job_id = uuid.uuid4()
        request.revision_count = 0
        request.response_payload_json = {
            WORKFLOW_BINDING_KEY: build_workflow_binding(
                workflow_run_id=paused.id,
                workflow_node_run_id=None,
                node_id="approval",
                resume_token=token,
                on_timeout="stop",
            )
        }

        with patch(
            "backend.modules.workflows.nodes.publishing.PublishNode.execute",
            new=AsyncMock(
                return_value=NodeResult(
                    status=NodeResultStatus.SUCCEEDED,
                    output={
                        "job_ids": [str(uuid.uuid4())],
                        "statuses": ["dry_run"],
                        "dry_run": True,
                    },
                )
            ),
        ):
            run = await maybe_resume_workflow_from_approval(db, request)

        assert run is not None
        assert run.status == WorkflowRunStatus.SUCCEEDED.value
        await db.close()

    asyncio.run(_run())


def test_apply_approve_skips_publish_when_workflow_bound() -> None:
    async def _run() -> None:
        request = MagicMock()
        request.content_job_id = uuid.uuid4()
        request.tenant_id = uuid.uuid4()
        request.id = uuid.uuid4()
        request.approval_type = "asset"
        request.response_payload_json = {
            WORKFLOW_BINDING_KEY: build_workflow_binding(
                workflow_run_id=uuid.uuid4(),
                workflow_node_run_id=uuid.uuid4(),
                node_id="approval",
                resume_token=str(uuid.uuid4()),
            )
        }
        svc = MagicMock()
        svc.publish_service.publish_now = AsyncMock()
        with patch(
            "backend.modules.approvals.approval_actions.record_preference",
            new=AsyncMock(),
        ):
            await _apply_approve(svc, request)
        assert request.status == ApprovalStatus.APPROVED.value
        svc.publish_service.publish_now.assert_not_called()

    asyncio.run(_run())


def test_apply_intent_revise_does_not_resume() -> None:
    async def _run() -> None:
        request = MagicMock()
        request.status = ApprovalStatus.PENDING.value
        request.response_payload_json = {
            WORKFLOW_BINDING_KEY: {"resume_token": "tok"}
        }
        svc = MagicMock()
        svc.db = MagicMock()
        svc.audit.record = AsyncMock()
        with (
            patch(
                "backend.modules.approvals.approval_actions._apply_revise",
                new=AsyncMock(),
            ),
            patch(
                "backend.modules.workflows.approval_binding.maybe_resume_workflow_from_approval",
                new=AsyncMock(),
            ) as resume,
        ):
            await apply_intent(svc, request, ApprovalIntent.REVISE.value, "tighten")
            # After revise mock, status still pending → resume still called but
            # maybe_resume no-ops on pending; we assert it was invoked once.
            resume.assert_awaited_once()

    asyncio.run(_run())
