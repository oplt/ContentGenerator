"""Phase 2 — durable retry classification, backoff, and side-effect idempotency."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Table, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.content_strategy.models import Brand
from backend.modules.identity_access.models import Tenant
from backend.modules.operations.models import TaskExecution
from backend.modules.publishing.models import SocialAccount
from backend.modules.workflows.engine import WorkflowEngine
from backend.modules.workflows.engine_node_task import execute_claimed_node_run
from backend.modules.workflows.models import Automation, WorkflowDefinition, WorkflowVersion
from backend.modules.workflows.node_retry import (
    ErrorClass,
    apply_side_effect_idempotency,
    classify_exception,
    compute_backoff_seconds,
    should_retry,
)
from backend.modules.workflows.nodes.base import (
    NodeResult,
    NodeResultStatus,
    RetryPolicyDefaults,
)
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
)
from backend.modules.workflows import run_repository as node_claims


@pytest.fixture(autouse=True)
def _fresh_registry():
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


def test_classify_timeout_and_auth() -> None:
    assert classify_exception(TimeoutError("slow")) is ErrorClass.TIMEOUT
    assert classify_exception(RuntimeError("HTTP 429 rate limit")) is ErrorClass.RATE_LIMITED
    assert classify_exception(RuntimeError("401 unauthorized")) is ErrorClass.AUTHENTICATION
    assert classify_exception(RuntimeError("validation failed")) is ErrorClass.VALIDATION


def test_should_retry_respects_policy_and_non_retryable() -> None:
    policy = RetryPolicyDefaults(max_attempts=3, retry_on=["transient", "timeout"])
    assert should_retry(error_class="transient", attempt=1, policy=policy)
    assert not should_retry(error_class="validation", attempt=1, policy=policy)
    assert not should_retry(error_class="transient", attempt=3, policy=policy)


def test_backoff_grows_and_is_bounded() -> None:
    policy = RetryPolicyDefaults(backoff_seconds=2.0, max_backoff_seconds=10.0)
    with patch("backend.modules.workflows.node_retry.random.uniform", return_value=0.0):
        assert compute_backoff_seconds(1, policy) == 2.0
        assert compute_backoff_seconds(2, policy) == 4.0
        assert compute_backoff_seconds(4, policy) == 10.0


def test_publish_idempotency_injected_from_execution_key() -> None:
    merged = apply_side_effect_idempotency(
        node_type="publish",
        inputs={"content_job_id": str(uuid.uuid4())},
        execution_key="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee:publish:v1",
    )
    assert merged["idempotency_key"].startswith("aaaaaaaa")


def _graph() -> dict[str, Any]:
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
                    TaskExecution.__table__,
                    WorkflowRun.__table__,
                    WorkflowNodeRun.__table__,
                ]),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False)()


async def _seed(db: AsyncSession) -> tuple[Tenant, WorkflowVersion]:
    tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
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
        graph_json=_graph(),
        published_at=datetime.now(timezone.utc),
    )
    db.add(version)
    await db.flush()
    return tenant, version


def _mock_llm(text: str = "ok") -> MagicMock:
    llm = MagicMock()

    async def _agen(*_a, **_k):  # type: ignore[no-untyped-def]
        return text

    llm.generate_text = _agen
    llm.provider_name = "mock"
    return llm


def test_transient_failure_schedules_retry_not_run_failure() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, version = await _seed(db)
        engine = WorkflowEngine(db)
        calls = {"n": 0}

        async def _flaky(self, context, inputs, config):  # type: ignore[no-untyped-def]
            _ = (self, context, inputs, config)
            calls["n"] += 1
            if calls["n"] == 1:
                return NodeResult(
                    status=NodeResultStatus.FAILED,
                    error={"code": "timeout", "message": "provider timeout"},
                )
            return NodeResult(
                status=NodeResultStatus.SUCCEEDED,
                output={"text": "recovered", "provider": "mock"},
            )

        with (
            patch(
                "backend.modules.workflows.nodes.text.get_llm_provider",
                return_value=_mock_llm(),
            ),
            patch(
                "backend.modules.workflows.nodes.text.GenerateTextNode.execute",
                new=_flaky,
            ),
        ):
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                trigger_payload={"prompt": "retry me"},
                advance=True,
            )

        assert run.status == WorkflowRunStatus.SUCCEEDED.value
        nodes = {n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)}
        assert nodes["generate"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        assert nodes["generate"].attempt >= 2
        assert calls["n"] >= 2
        await db.close()

    asyncio.run(_run())


def test_validation_failure_does_not_retry() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, version = await _seed(db)
        engine = WorkflowEngine(db)
        calls = {"n": 0}

        async def _bad(self, context, inputs, config):  # type: ignore[no-untyped-def]
            _ = (self, context, inputs, config)
            calls["n"] += 1
            return NodeResult(
                status=NodeResultStatus.FAILED,
                error={"code": "validation", "message": "bad input"},
            )

        with (
            patch(
                "backend.modules.workflows.nodes.text.get_llm_provider",
                return_value=_mock_llm(),
            ),
            patch(
                "backend.modules.workflows.nodes.text.GenerateTextNode.execute",
                new=_bad,
            ),
        ):
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                trigger_payload={"prompt": "no retry"},
                advance=True,
            )

        assert run.status == WorkflowRunStatus.FAILED.value
        nodes = {n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)}
        assert nodes["generate"].status == WorkflowNodeRunStatus.FAILED.value
        assert nodes["generate"].error_class == "validation"
        assert nodes["generate"].last_error
        assert calls["n"] == 1
        await db.close()

    asyncio.run(_run())


def test_claimed_execute_persists_error_class_on_retry() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, version = await _seed(db)
        engine = WorkflowEngine(db)
        run = await engine.start_run(
            tenant_id=tenant.id,
            workflow_version_id=version.id,
            trigger_payload={"prompt": "x"},
            advance=False,
        )
        nodes = await engine.runs.list_node_runs(tenant.id, run.id)
        trigger = next(n for n in nodes if n.node_id == "trigger")
        claimed = await node_claims.claim_ready_node(
            db, tenant_id=tenant.id, workflow_run_id=run.id, node_run_id=trigger.id
        )
        assert claimed is not None

        async def _boom(self, context, inputs, config):  # type: ignore[no-untyped-def]
            _ = (self, context, inputs, config)
            raise TimeoutError("upstream timeout")

        # Force generate path unused; fail trigger via manual_trigger patch is awkward —
        # execute claimed trigger normally then fail generate in a second claim.
        await execute_claimed_node_run(
            engine,
            tenant_id=tenant.id,
            workflow_run_id=run.id,
            node_run_id=claimed.id,
            claim_token=str(claimed.claim_token),
            enqueue_followups=False,
        )
        nodes = await engine.runs.list_node_runs(tenant.id, run.id)
        generate = next(n for n in nodes if n.node_id == "generate")
        assert generate.status == WorkflowNodeRunStatus.READY.value
        claimed_g = await node_claims.claim_ready_node(
            db, tenant_id=tenant.id, workflow_run_id=run.id, node_run_id=generate.id
        )
        assert claimed_g is not None
        with patch(
            "backend.modules.workflows.nodes.text.GenerateTextNode.execute",
            new=_boom,
        ):
            await execute_claimed_node_run(
                engine,
                tenant_id=tenant.id,
                workflow_run_id=run.id,
                node_run_id=claimed_g.id,
                claim_token=str(claimed_g.claim_token),
                enqueue_followups=False,
            )
        refreshed = await engine.runs.get_node_run_by_id(tenant.id, claimed_g.id)
        assert refreshed is not None
        assert refreshed.status == WorkflowNodeRunStatus.READY.value
        assert refreshed.error_class == "timeout"
        assert refreshed.last_error
        assert refreshed.next_attempt_at is not None
        await db.close()

    asyncio.run(_run())
