"""Phase 15 — dry-run + single-node test."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, patch

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
from backend.modules.workflows.models import Automation, WorkflowDefinition, WorkflowVersion
from backend.modules.workflows.node_tester import WorkflowNodeTester
from backend.modules.workflows.nodes.base import NodeResult, NodeResultStatus
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowRun, WorkflowRunStatus
from backend.modules.workflows.testing_support import (
    merge_dry_run_config,
    mock_generation_result,
    testing_flags as build_testing_flags,
)


@pytest.fixture(autouse=True)
def _fresh_registry() -> Iterator[None]:
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


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
                    ],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


async def _seed_published(
    db: AsyncSession, graph: dict[str, Any]
) -> tuple[Tenant, WorkflowVersion]:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    await db.flush()
    definition = WorkflowDefinition(
        tenant_id=tenant.id,
        name="Test",
        slug=f"test-{uuid.uuid4().hex[:8]}",
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


def test_merge_dry_run_config_forces_flag() -> None:
    assert merge_dry_run_config({"foo": 1}, dry_run=True)["dry_run"] is True
    assert "dry_run" not in merge_dry_run_config({"foo": 1}, dry_run=False)


def test_mock_generation_text() -> None:
    result = mock_generation_result("generate_text", {"prompt": "hello"})
    assert result.status == NodeResultStatus.SUCCEEDED
    assert result.output["provider"] == "mock"
    assert "hello" in result.output["text"]


def test_testing_flag_helper() -> None:
    flags = build_testing_flags(dry_run=True, mock_generation=True, simulate_approval=True)
    assert flags["dry_run"] is True
    assert flags["mock_generation"] is True
    assert flags["simulate_approval"] is True


def test_node_tester_mocks_generation() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        result = await WorkflowNodeTester(db).test_node(
            tenant_id=tenant.id,
            node_type="generate_text",
            inputs={"prompt": "chess tip"},
            mock_generation=True,
        )
        assert result.status == "succeeded"
        assert result.output["provider"] == "mock"
        await db.close()

    asyncio.run(_run())


def test_node_tester_simulates_approval_in_dry_run() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        result = await WorkflowNodeTester(db).test_node(
            tenant_id=tenant.id,
            node_type="approval",
            inputs={"content_job_id": str(uuid.uuid4())},
            dry_run=True,
        )
        assert result.status == "succeeded"
        assert result.output.get("simulated") is True
        await db.close()

    asyncio.run(_run())


def test_dry_run_mocks_generation_without_llm() -> None:
    async def _run() -> None:
        db = await _async_session()
        graph = {
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
        tenant, version = await _seed_published(db, graph)
        with patch("backend.modules.workflows.nodes.text.get_llm_provider") as llm:
            llm.return_value.generate_text = AsyncMock(return_value="SHOULD_NOT_CALL")
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                dry_run=True,
                mock_generation=True,
                trigger_payload={"prompt": "daily tip"},
            )
        assert run.trigger_type == "dry_run"
        testing = cast(dict[str, object], run.context_snapshot["testing"])
        assert testing["mock_generation"] is True
        assert run.status == WorkflowRunStatus.SUCCEEDED.value
        nodes = await engine.runs.list_node_runs(tenant.id, run.id)
        gen = next(n for n in nodes if n.node_id == "generate")
        assert gen.output_json.get("provider") == "mock"
        llm.return_value.generate_text.assert_not_called()
        await db.close()

    asyncio.run(_run())


def test_simulate_approval_auto_resumes() -> None:
    async def _run() -> None:
        db = await _async_session()
        graph = {
            "nodes": [
                {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
                {"id": "approval", "type": "approval", "version": 1, "config": {}},
            ],
            "edges": [{"source": "trigger", "target": "approval"}],
        }
        tenant, version = await _seed_published(db, graph)
        job_id = uuid.uuid4()

        async def _fake_execute(self, context, inputs, config):  # noqa: ANN001
            _ = self, context, inputs, config
            return NodeResult(
                status=NodeResultStatus.WAITING,
                output={"approval_request_id": str(uuid.uuid4())},
                waiting_reason="approval_pending",
            )

        with patch(
            "backend.modules.workflows.nodes.approval.ApprovalNode.execute",
            new=_fake_execute,
        ):
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                dry_run=True,
                simulate_approval=True,
                trigger_payload={"content_job_id": str(job_id)},
            )
        nodes = await engine.runs.list_node_runs(tenant.id, run.id)
        approval = next(n for n in nodes if n.node_id == "approval")
        assert approval.status == "succeeded"
        assert run.status == WorkflowRunStatus.SUCCEEDED.value
        await db.close()

    asyncio.run(_run())
