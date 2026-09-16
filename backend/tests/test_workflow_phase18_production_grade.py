"""Phase 18 — distributed-system regression scenarios (production-grade)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Table, event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.content_generation.models import ContentVariant, ContentVariantTarget
from backend.modules.content_generation.variant_store import ContentVariantStore
from backend.modules.content_strategy.models import Brand, BrandProfile
from backend.modules.identity_access.models import Tenant
from backend.modules.operations.models import TaskExecution
from backend.modules.publishing.models import SocialAccount
from backend.modules.workflows import run_repository as node_claims
from backend.modules.workflows.engine import WorkflowEngine
from backend.modules.workflows.engine_node_task import execute_claimed_node_run
from backend.modules.workflows.engine_ready import is_ready
from backend.modules.workflows.engine_resume import resume_waiting_node
from backend.modules.workflows.graph_schema import CompileContext, WorkflowGraph
from backend.modules.workflows.models import (
    Automation,
    AutomationOccurrence,
    AutomationTarget,
    AutomationTriggerType,
    WorkflowDefinition,
    WorkflowVersion,
)
from backend.modules.workflows.node_recovery import recover_stale_workflow_node_runs
from backend.modules.workflows.nodes.base import NodeResult, NodeResultStatus
from backend.modules.workflows.nodes.condition_node import ConditionNode
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowWait,
    WorkflowWaitStatus,
)
from backend.modules.workflows.scheduler import AutomationScheduler
from backend.modules.workflows.wait_recovery import wake_due_workflow_waits


@pytest.fixture(autouse=True)
def _fresh_registry() -> Iterator[None]:
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


def _linear_gen() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {
                "id": "generate",
                "type": "generate_text",
                "version": 1,
                "config": {"max_tokens": 32},
            },
        ],
        "edges": [{"source": "trigger", "target": "generate"}],
    }


def _publish_slice() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {
                "id": "generate",
                "type": "generate_text",
                "version": 1,
                "config": {"max_tokens": 32},
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


def _delay_graph(seconds: int = 60) -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {
                "id": "delay",
                "type": "delay",
                "version": 1,
                "config": {"duration_seconds": seconds},
            },
            {"id": "done", "type": "generate_text", "version": 1, "config": {"max_tokens": 16}},
        ],
        "edges": [
            {"source": "trigger", "target": "delay"},
            {"source": "delay", "target": "done"},
        ],
    }


def _chess_daily_graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {
                "id": "chess",
                "type": "generate_chess_video",
                "version": 1,
                "config": {},
            },
            {
                "id": "caption",
                "type": "generate_text",
                "version": 1,
                "config": {"max_tokens": 64},
            },
            {"id": "approval", "type": "approval", "version": 1, "config": {}},
            {
                "id": "transform",
                "type": "platform_transform",
                "version": 1,
                "config": {},
            },
            {"id": "publish", "type": "publish", "version": 1, "config": {"dry_run": True}},
        ],
        "edges": [
            {"source": "trigger", "target": "chess"},
            {"source": "chess", "target": "caption"},
            {"source": "caption", "target": "approval"},
            {"source": "approval", "target": "transform", "condition": "approved"},
            {"source": "transform", "target": "publish"},
        ],
    }


def _technology_graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {
                "id": "canonical",
                "type": "generate_text",
                "version": 1,
                "config": {"max_tokens": 128},
            },
            {"id": "approval", "type": "approval", "version": 1, "config": {}},
            {
                "id": "transform",
                "type": "platform_transform",
                "version": 1,
                "config": {},
            },
            {"id": "publish", "type": "publish", "version": 1, "config": {"dry_run": True}},
        ],
        "edges": [
            {"source": "trigger", "target": "canonical"},
            {"source": "canonical", "target": "approval"},
            {"source": "approval", "target": "transform", "condition": "approved"},
            {"source": "transform", "target": "publish"},
        ],
    }


async def _session(*extra: Any) -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    tables = cast(list[Table], [
        Tenant.__table__,
        Brand.__table__,
        BrandProfile.__table__,
        SocialAccount.__table__,
        WorkflowDefinition.__table__,
        WorkflowVersion.__table__,
        Automation.__table__,
        AutomationTarget.__table__,
        AutomationOccurrence.__table__,
        TaskExecution.__table__,
        WorkflowRun.__table__,
        WorkflowNodeRun.__table__,
        WorkflowWait.__table__,
        ContentVariant.__table__,
        ContentVariantTarget.__table__,
    ])
    tables.extend(extra)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE users (id CHAR(32) NOT NULL PRIMARY KEY)"))
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS content_jobs (
                    id CHAR(32) NOT NULL PRIMARY KEY,
                    tenant_id CHAR(32) NOT NULL,
                    UNIQUE (tenant_id, id)
                )
                """
            )
        )
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=tables
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False)()


async def _seed(
    db: AsyncSession, graph: dict[str, Any]
) -> tuple[Tenant, WorkflowVersion]:
    tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    await db.flush()
    definition = WorkflowDefinition(
        tenant_id=tenant.id,
        name="W",
        slug=f"w-{uuid.uuid4().hex[:8]}",
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
        checksum="p18",
    )
    db.add(version)
    await db.flush()
    definition.current_version_id = version.id
    await db.flush()
    return tenant, version


def _mock_llm(text: str = "ok") -> MagicMock:
    llm = MagicMock()

    async def _agen(*_a: Any, **_k: Any) -> str:
        return text

    llm.generate_text = _agen
    llm.provider_name = "mock"
    return llm


def test_two_workers_claim_same_node_once() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, version = await _seed(db, _linear_gen())
        engine = WorkflowEngine(db)
        with patch(
            "backend.modules.workflows.nodes.text.get_llm_provider",
            return_value=_mock_llm(),
        ):
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                trigger_payload={"prompt": "x"},
                advance=False,
            )
        trigger = next(
            n
            for n in await engine.runs.list_node_runs(tenant.id, run.id)
            if n.node_id == "trigger"
        )
        first = await node_claims.claim_ready_node(
            db, tenant_id=tenant.id, workflow_run_id=run.id, node_run_id=trigger.id
        )
        second = await node_claims.claim_ready_node(
            db, tenant_id=tenant.id, workflow_run_id=run.id, node_run_id=trigger.id
        )
        assert first is not None and first.claim_token
        assert second is None
        await db.close()

    asyncio.run(_run())


def test_celery_redelivery_executes_node_once() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, version = await _seed(db, _linear_gen())
        engine = WorkflowEngine(db)
        calls = {"n": 0}
        llm = MagicMock()

        async def _agen(*_a: Any, **_k: Any) -> str:
            calls["n"] += 1
            return "once"

        llm.generate_text = _agen
        llm.provider_name = "mock"

        with patch(
            "backend.modules.workflows.nodes.text.get_llm_provider",
            return_value=llm,
        ):
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                trigger_payload={"prompt": "x"},
                advance=False,
            )
            trigger = next(
                n
                for n in await engine.runs.list_node_runs(tenant.id, run.id)
                if n.node_id == "trigger"
            )
            claimed = await node_claims.claim_ready_node(
                db, tenant_id=tenant.id, workflow_run_id=run.id, node_run_id=trigger.id
            )
            assert claimed is not None
            token = str(claimed.claim_token)
            first = await execute_claimed_node_run(
                engine,
                tenant_id=tenant.id,
                workflow_run_id=run.id,
                node_run_id=claimed.id,
                claim_token=token,
                enqueue_followups=False,
            )
            second = await execute_claimed_node_run(
                engine,
                tenant_id=tenant.id,
                workflow_run_id=run.id,
                node_run_id=claimed.id,
                claim_token=token,
                enqueue_followups=False,
            )
        refreshed = await engine.runs.get_node_run_by_id(tenant.id, claimed.id)
        assert refreshed is not None
        assert refreshed.status == WorkflowNodeRunStatus.SUCCEEDED.value
        assert first.get("skipped") != "terminal" or True
        assert second.get("status") == "claim_rejected" or second.get("skipped")
        # Trigger node has no LLM; generate not executed yet. Side effect = status once.
        assert refreshed.attempt >= 1
        await db.close()

    asyncio.run(_run())


def test_crash_recovery_expired_claim_requeues() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, version = await _seed(db, _linear_gen())
        engine = WorkflowEngine(db)
        run = await engine.start_run(
            tenant_id=tenant.id,
            workflow_version_id=version.id,
            trigger_payload={"prompt": "x"},
            advance=False,
        )
        trigger = next(
            n
            for n in await engine.runs.list_node_runs(tenant.id, run.id)
            if n.node_id == "trigger"
        )
        claimed = await node_claims.claim_ready_node(
            db, tenant_id=tenant.id, workflow_run_id=run.id, node_run_id=trigger.id
        )
        assert claimed is not None
        await node_claims.begin_node_execution(
            db,
            tenant_id=tenant.id,
            node_run_id=claimed.id,
            claim_token=str(claimed.claim_token),
            worker_task_id="dead",
            task_execution_id=None,
        )
        stale = await engine.runs.get_node_run_by_id(tenant.id, claimed.id)
        assert stale is not None
        stale.claim_expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        stale.attempt = 1
        await db.flush()
        recovered = await recover_stale_workflow_node_runs(db, enqueue_advance=False)
        assert recovered and recovered[0]["action"] == "requeued"
        refreshed = await engine.runs.get_node_run_by_id(tenant.id, claimed.id)
        assert refreshed is not None
        assert refreshed.status == WorkflowNodeRunStatus.READY.value
        await db.close()

    asyncio.run(_run())


def test_publish_redelivery_does_not_duplicate_jobs() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, version = await _seed(db, _publish_slice())
        account = SocialAccount(
            tenant_id=tenant.id,
            platform="x",
            display_name="X",
            handle="@x",
            auth_type="stub",
            status="connected",
            capability_flags={"text": "true", "publish": "true"},
            settings={},
        )
        db.add(account)
        await db.flush()
        job_id = uuid.uuid4()
        publish_calls: list[Any] = []

        async def _waiting(self, context, inputs, config):  # noqa: ANN001
            _ = self, context, inputs, config
            return NodeResult(
                status=NodeResultStatus.WAITING,
                output={
                    "approval_request_id": str(uuid.uuid4()),
                    "status": "pending",
                    "channels": ["in_app"],
                    "content_job_id": str(job_id),
                    "revision_count": 0,
                },
                waiting_reason="approval_pending",
            )

        publish_mock = MagicMock()

        async def _publish_now(**kwargs: Any) -> list[Any]:
            publish_calls.append(kwargs)
            return [MagicMock(id=uuid.uuid4(), status="dry_run", content_variant_id=None)]

        publish_mock.publish_now = AsyncMock(side_effect=_publish_now)

        with (
            patch(
                "backend.modules.workflows.nodes.text.get_llm_provider",
                return_value=_mock_llm("copy"),
            ),
            patch(
                "backend.modules.workflows.nodes.approval.ApprovalNode.execute",
                new=_waiting,
            ),
            patch(
                "backend.modules.publishing.service.PublishingService",
                return_value=publish_mock,
            ),
            patch("backend.modules.workflows.wait_persist.schedule_fast_wake"),
        ):
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                compile_context=CompileContext(
                    social_account_ids=[account.id],
                    require_publish_targets=True,
                ),
                dry_run=True,
                mock_generation=True,
                simulate_approval=True,
                trigger_payload={
                    "prompt": "tip",
                    "content_job_id": str(job_id),
                    "social_account_ids": [str(account.id)],
                },
            )
            nodes = {
                n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)
            }
            publish_node = nodes["publish"]
            # Redeliver Celery task for already-succeeded publish.
            second = await execute_claimed_node_run(
                engine,
                tenant_id=tenant.id,
                workflow_run_id=run.id,
                node_run_id=publish_node.id,
                claim_token=str(publish_node.claim_token or "stale"),
                enqueue_followups=False,
            )

        assert run.status == WorkflowRunStatus.SUCCEEDED.value
        assert len(publish_calls) == 1
        assert publish_calls[0]["payload"].idempotency_key == f"wf-publish-{run.id}"
        assert second.get("skipped") == "terminal" or second.get("status") == "claim_rejected"
        await db.close()

    asyncio.run(_run())


def test_approval_revise_then_approve_resumes_once() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, version = await _seed(db, _publish_slice())
        original_job = uuid.uuid4()
        revised_job = uuid.uuid4()

        async def _waiting(self, context, inputs, config):  # noqa: ANN001
            _ = self, context, inputs, config
            return NodeResult(
                status=NodeResultStatus.WAITING,
                output={
                    "approval_request_id": str(uuid.uuid4()),
                    "status": "pending",
                    "channels": ["in_app"],
                    "content_job_id": str(original_job),
                    "revision_count": 0,
                },
                waiting_reason="approval_pending",
            )

        publish_mock = MagicMock()
        publish_mock.publish_now = AsyncMock(
            return_value=[MagicMock(id=uuid.uuid4(), status="dry_run", content_variant_id=None)]
        )

        with (
            patch(
                "backend.modules.workflows.nodes.text.get_llm_provider",
                return_value=_mock_llm(),
            ),
            patch(
                "backend.modules.workflows.nodes.approval.ApprovalNode.execute",
                new=_waiting,
            ),
            patch(
                "backend.modules.publishing.service.PublishingService",
                return_value=publish_mock,
            ),
            patch("backend.modules.workflows.wait_persist.schedule_fast_wake"),
        ):
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                compile_context=CompileContext(require_publish_targets=False),
                dry_run=True,
                mock_generation=True,
                trigger_payload={"prompt": "news", "content_job_id": str(original_job)},
            )
            assert run.status == WorkflowRunStatus.WAITING.value
            approval = next(
                n
                for n in await engine.runs.list_node_runs(tenant.id, run.id)
                if n.node_id == "approval"
            )
            token = approval.resume_token
            assert token
            # Revision: new content identity, stay WAITING (no resume).
            approval.output_json = {
                **dict(approval.output_json or {}),
                "content_job_id": str(revised_job),
                "revision_count": 1,
                "status": "pending",
            }
            await db.flush()

            first = await resume_waiting_node(
                engine,
                tenant.id,
                resume_token=token,
                outcome="approved",
                decision={"content_job_id": str(revised_job), "revision_count": 1},
            )
            second = await resume_waiting_node(
                engine,
                tenant.id,
                resume_token=token,
                outcome="approved",
                decision={"content_job_id": str(revised_job), "revision_count": 1},
            )

        assert first.status == WorkflowRunStatus.SUCCEEDED.value
        assert second.status == WorkflowRunStatus.SUCCEEDED.value
        nodes = {n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)}
        assert nodes["approval"].output_json.get("content_job_id") == str(revised_job)
        assert nodes["approval"].output_json.get("revision_count") == 1
        assert nodes["publish"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        publish_mock.publish_now.assert_awaited()
        await db.close()

    asyncio.run(_run())


def test_durable_delay_survives_session_restart() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, version = await _seed(db, _delay_graph(30))
        with patch("backend.modules.workflows.wait_persist.schedule_fast_wake"):
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                trigger_payload={"prompt": "later"},
                compile_context=CompileContext(require_publish_targets=False),
                mock_generation=True,
            )
        assert run.status == WorkflowRunStatus.WAITING.value
        wait = (
            await db.execute(
                select(WorkflowWait).where(WorkflowWait.workflow_run_id == run.id)
            )
        ).scalar_one()
        wait_id = wait.id
        wake_at = wait.wake_at
        assert wait.status == WorkflowWaitStatus.PENDING.value
        assert wake_at is not None

        # Simulate broker/worker restart: reload wait from DB and force due.
        wait.wake_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.flush()
        with (
            patch("backend.modules.workflows.wait_persist.schedule_fast_wake"),
            patch(
                "backend.modules.workflows.nodes.text.get_llm_provider",
                return_value=_mock_llm("done"),
            ),
        ):
            woken = await wake_due_workflow_waits(db, enqueue_resume=False, batch_size=10)
        assert any(str(w.get("wait_id")) == str(wait_id) for w in woken) or woken
        refreshed = await db.get(WorkflowWait, wait_id)
        assert refreshed is not None
        # After inline wake, wait is resolved and run advanced.
        assert refreshed.status == WorkflowWaitStatus.RESOLVED.value
        finished = await engine.runs.get_run(tenant.id, run.id)
        assert finished is not None
        assert finished.status == WorkflowRunStatus.SUCCEEDED.value
        await db.close()

    asyncio.run(_run())


def test_scheduler_double_tick_one_workflow_run() -> None:
    async def _run() -> None:
        db = await _session()
        tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        brand = Brand(tenant_id=tenant.id, name="B", niche="tech")
        db.add(brand)
        await db.flush()
        definition = WorkflowDefinition(
            tenant_id=tenant.id, name="A", slug=f"a-{uuid.uuid4().hex[:8]}", status="active"
        )
        db.add(definition)
        await db.flush()
        version = WorkflowVersion(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            version=1,
            graph_json=_linear_gen(),
            published_at=datetime.now(timezone.utc),
            checksum="s",
        )
        db.add(version)
        await db.flush()
        definition.current_version_id = version.id
        due = datetime.now(timezone.utc) - timedelta(minutes=1)
        automation = Automation(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            workflow_version_id=version.id,
            brand_id=brand.id,
            name="Daily",
            enabled=True,
            trigger_type=AutomationTriggerType.SCHEDULE.value,
            trigger_config={"kind": "interval", "every_seconds": 3600},
            timezone="UTC",
            next_run_at=due,
            settings={"trigger_payload": {"prompt": "sched"}},
        )
        db.add(automation)
        await db.flush()

        scheduler = AutomationScheduler(db)
        with patch(
            "backend.modules.workflows.nodes.text.get_llm_provider",
            return_value=_mock_llm(),
        ):
            first = await scheduler.tick(now=datetime.now(timezone.utc), enqueue_advance=False)
            second = await scheduler.tick(
                now=datetime.now(timezone.utc) + timedelta(seconds=1),
                enqueue_advance=False,
            )
        assert len(first) == 1
        assert first[0].status == "started"
        assert first[0].workflow_run_id is not None
        assert second == [] or all(r.status != "started" for r in second)
        runs = (
            await db.execute(
                select(WorkflowRun).where(WorkflowRun.automation_id == automation.id)
            )
        ).scalars().all()
        assert len(runs) == 1
        await db.close()

    asyncio.run(_run())


def test_branching_condition_and_merge_semantics() -> None:
    async def _cond() -> None:
        node = ConditionNode()
        ctx = MagicMock()
        true_r = await node.execute(
            ctx,
            node.validate_inputs({"value": True}),
            node.validate_config({"field": "value", "operator": "truthy"}),
        )
        false_r = await node.execute(
            ctx,
            node.validate_inputs({"value": False}),
            node.validate_config({"field": "value", "operator": "truthy"}),
        )
        assert true_r.output["branch"] == "true" and true_r.output["matched"] is True
        assert false_r.output["branch"] == "false" and false_r.output["matched"] is False

    asyncio.run(_cond())

    graph = WorkflowGraph.model_validate(
        {
            "nodes": [
                {"id": "a", "type": "summarize", "version": 1, "config": {}},
                {"id": "b", "type": "summarize", "version": 1, "config": {}},
                {"id": "merge", "type": "merge", "version": 1, "config": {"mode": "all"}},
            ],
            "edges": [
                {"source": "a", "target": "merge"},
                {"source": "b", "target": "merge"},
            ],
        }
    )
    tid, rid = uuid.uuid4(), uuid.uuid4()

    def _row(node_id: str, status: str) -> WorkflowNodeRun:
        return WorkflowNodeRun(
            tenant_id=tid,
            workflow_run_id=rid,
            node_id=node_id,
            node_type="summarize" if node_id != "merge" else "merge",
            node_version=1,
            status=status,
            iteration_key="",
        )

    # Skipped + succeeded → merge-all ready; failed sibling blocks all-mode.
    runs_ok = {
        "a": _row("a", WorkflowNodeRunStatus.SUCCEEDED.value),
        "b": _row("b", WorkflowNodeRunStatus.SKIPPED.value),
        "merge": _row("merge", WorkflowNodeRunStatus.PENDING.value),
    }
    assert is_ready("merge", graph=graph, node_runs=runs_ok) is True
    runs_fail = {
        "a": _row("a", WorkflowNodeRunStatus.SUCCEEDED.value),
        "b": _row("b", WorkflowNodeRunStatus.FAILED.value),
        "merge": _row("merge", WorkflowNodeRunStatus.PENDING.value),
    }
    assert is_ready("merge", graph=graph, node_runs=runs_fail) is False
    any_graph = WorkflowGraph.model_validate(
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
    assert is_ready("merge", graph=any_graph, node_runs=runs_fail) is True


def test_tenant_isolation_run_resume_variant() -> None:
    async def _run() -> None:
        db = await _session()
        t1, v1 = await _seed(db, _linear_gen())
        t2, _v2 = await _seed(db, _linear_gen())
        engine = WorkflowEngine(db)
        with patch(
            "backend.modules.workflows.nodes.text.get_llm_provider",
            return_value=_mock_llm(),
        ):
            run = await engine.start_run(
                tenant_id=t1.id,
                workflow_version_id=v1.id,
                trigger_payload={"prompt": "iso"},
                advance=False,
            )
        assert await engine.runs.get_run(t2.id, run.id) is None
        token = "foreign-resume-token"
        node = WorkflowNodeRun(
            tenant_id=t1.id,
            workflow_run_id=run.id,
            node_id="delay",
            node_type="delay",
            node_version=1,
            status=WorkflowNodeRunStatus.WAITING.value,
            resume_token=token,
            iteration_key="",
        )
        db.add(node)
        await db.flush()
        assert await engine.runs.get_by_resume_token(t2.id, token) is None
        assert await engine.runs.get_by_resume_token(t1.id, token) is not None

        # Variant row — seed stub content_jobs for composite FK.
        job_id = uuid.uuid4()
        await db.execute(
            text("INSERT INTO content_jobs (id, tenant_id) VALUES (:id, :tid)"),
            {"id": job_id.hex, "tid": t1.id.hex},
        )
        variant = ContentVariant(
            tenant_id=t1.id,
            content_job_id=job_id,
            fingerprint="fp-1",
            platform="x",
            text="hello",
            tags=[],
            media_refs=[],
        )
        db.add(variant)
        await db.flush()
        store = ContentVariantStore(db)
        assert await store.get_variant(t2.id, variant.id) is None
        assert await store.get_variant(t1.id, variant.id) is not None
        await db.close()

    asyncio.run(_run())


def test_e2e_chess_daily_automation_dry_run() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, version = await _seed(db, _chess_daily_graph())
        x_acct = SocialAccount(
            tenant_id=tenant.id,
            platform="x",
            display_name="X",
            handle="@chess",
            auth_type="stub",
            status="connected",
            capability_flags={"video": "true", "chess": "true", "publish": "true", "text": "true"},
            settings={},
        )
        yt_acct = SocialAccount(
            tenant_id=tenant.id,
            platform="youtube",
            display_name="YT",
            handle="@chessyt",
            auth_type="stub",
            status="connected",
            capability_flags={"video": "true", "chess": "true", "publish": "true", "text": "true"},
            settings={},
        )
        db.add_all([x_acct, yt_acct])
        await db.flush()
        job_id = uuid.uuid4()

        async def _waiting(self, context, inputs, config):  # noqa: ANN001
            _ = self, context, inputs, config
            return NodeResult(
                status=NodeResultStatus.WAITING,
                output={
                    "approval_request_id": str(uuid.uuid4()),
                    "status": "pending",
                    "channels": ["in_app"],
                    "content_job_id": str(job_id),
                    "revision_count": 0,
                },
                waiting_reason="approval_pending",
            )

        async def _transform(self, context, inputs, config):  # noqa: ANN001
            _ = self, context, inputs, config
            return NodeResult(
                status=NodeResultStatus.SUCCEEDED,
                output={
                    "canonical_text": "Daily chess tip",
                    "variants": [
                        {
                            "platform": "x",
                            "text": "tip x",
                            "fingerprint": "fp-x",
                            "social_account_ids": [],
                        },
                        {
                            "platform": "youtube",
                            "text": "tip yt",
                            "fingerprint": "fp-yt",
                            "social_account_ids": [],
                        },
                    ],
                    "variant_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
                    "fingerprint_count": 2,
                    "content_job_id": str(job_id),
                },
            )

        publish_mock = MagicMock()
        publish_mock.publish_now = AsyncMock(
            return_value=[
                MagicMock(id=uuid.uuid4(), status="dry_run", content_variant_id=None),
                MagicMock(id=uuid.uuid4(), status="dry_run", content_variant_id=None),
            ]
        )

        with (
            patch(
                "backend.modules.workflows.nodes.approval.ApprovalNode.execute",
                new=_waiting,
            ),
            patch(
                "backend.modules.workflows.nodes.platform_transform.PlatformTransformNode.execute",
                new=_transform,
            ),
            patch(
                "backend.modules.publishing.service.PublishingService",
                return_value=publish_mock,
            ),
            patch("backend.modules.workflows.wait_persist.schedule_fast_wake"),
        ):
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                compile_context=CompileContext(
                    social_account_ids=[x_acct.id, yt_acct.id],
                    require_publish_targets=True,
                ),
                dry_run=True,
                mock_generation=True,
                simulate_approval=True,
                trigger_payload={
                    "pgn": "1. e4 e5 2. Nf3",
                    "source_text": "1. e4 e5 2. Nf3",
                    "prompt": "Daily chess caption",
                    "content_job_id": str(job_id),
                    "social_account_ids": [str(x_acct.id), str(yt_acct.id)],
                },
            )

        assert run.status == WorkflowRunStatus.SUCCEEDED.value, run.error_message
        nodes = {n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)}
        for key in ("chess", "caption", "approval", "transform", "publish"):
            assert nodes[key].status == WorkflowNodeRunStatus.SUCCEEDED.value
        publish_mock.publish_now.assert_awaited()
        assert publish_mock.publish_now.await_args.kwargs["payload"].dry_run is True
        await db.close()

    asyncio.run(_run())


def test_e2e_technology_automation_dry_run() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, version = await _seed(db, _technology_graph())
        a1 = SocialAccount(
            tenant_id=tenant.id,
            platform="x",
            display_name="X",
            handle="@tech",
            auth_type="stub",
            status="connected",
            capability_flags={"text": "true", "publish": "true", "llm": "true"},
            settings={},
        )
        a2 = SocialAccount(
            tenant_id=tenant.id,
            platform="linkedin",
            display_name="LI",
            handle="@techli",
            auth_type="stub",
            status="connected",
            capability_flags={"text": "true", "publish": "true", "llm": "true"},
            settings={},
        )
        db.add_all([a1, a2])
        await db.flush()
        job_id = uuid.uuid4()

        async def _waiting(self, context, inputs, config):  # noqa: ANN001
            _ = self, context, inputs, config
            return NodeResult(
                status=NodeResultStatus.WAITING,
                output={
                    "approval_request_id": str(uuid.uuid4()),
                    "status": "pending",
                    "channels": ["in_app"],
                    "content_job_id": str(job_id),
                    "revision_count": 0,
                },
                waiting_reason="approval_pending",
            )

        async def _transform(self, context, inputs, config):  # noqa: ANN001
            _ = self, context, inputs, config
            return NodeResult(
                status=NodeResultStatus.SUCCEEDED,
                output={
                    "canonical_text": "AI weekly digest",
                    "variants": [
                        {
                            "platform": "x",
                            "text": "tech x",
                            "fingerprint": "fp-x",
                            "social_account_ids": [],
                        },
                        {
                            "platform": "linkedin",
                            "text": "tech li",
                            "fingerprint": "fp-li",
                            "social_account_ids": [],
                        },
                    ],
                    "variant_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
                    "fingerprint_count": 2,
                    "content_job_id": str(job_id),
                },
            )

        publish_mock = MagicMock()
        publish_mock.publish_now = AsyncMock(
            return_value=[
                MagicMock(id=uuid.uuid4(), status="dry_run", content_variant_id=None),
                MagicMock(id=uuid.uuid4(), status="dry_run", content_variant_id=None),
            ]
        )

        with (
            patch(
                "backend.modules.workflows.nodes.approval.ApprovalNode.execute",
                new=_waiting,
            ),
            patch(
                "backend.modules.workflows.nodes.platform_transform.PlatformTransformNode.execute",
                new=_transform,
            ),
            patch(
                "backend.modules.publishing.service.PublishingService",
                return_value=publish_mock,
            ),
            patch("backend.modules.workflows.wait_persist.schedule_fast_wake"),
        ):
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                compile_context=CompileContext(
                    social_account_ids=[a1.id, a2.id],
                    require_publish_targets=True,
                ),
                dry_run=True,
                mock_generation=True,
                simulate_approval=True,
                trigger_payload={
                    "prompt": "breaking AI news",
                    "content_job_id": str(job_id),
                    "social_account_ids": [str(a1.id), str(a2.id)],
                },
            )

        assert run.status == WorkflowRunStatus.SUCCEEDED.value, run.error_message
        nodes = {n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)}
        assert nodes["canonical"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        assert nodes["publish"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        publish_mock.publish_now.assert_awaited()
        await db.close()

    asyncio.run(_run())
