"""Phase 16 — end-to-end workflow cancellation."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
)
from backend.modules.workflows.workflow_cancellation import (
    cancel_run,
    request_celery_cancel,
    should_abort_node,
)


def _run(*, status: str = WorkflowRunStatus.RUNNING.value) -> WorkflowRun:
    now = datetime.now(timezone.utc)
    run = WorkflowRun(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        workflow_definition_id=uuid.uuid4(),
        workflow_version_id=uuid.uuid4(),
        trigger_type="manual",
        trigger_payload={},
        status=status,
        context_snapshot={},
        started_at=now,
        finished_at=None,
        error_message=None,
    )
    run.created_at = now
    run.updated_at = now
    return run


def _node(
    run: WorkflowRun,
    *,
    node_id: str,
    status: str,
    worker_task_id: str | None = None,
    task_execution_id: uuid.UUID | None = None,
) -> WorkflowNodeRun:
    now = datetime.now(timezone.utc)
    node = WorkflowNodeRun(
        id=uuid.uuid4(),
        tenant_id=run.tenant_id,
        workflow_run_id=run.id,
        node_id=node_id,
        node_type="generate_text",
        node_version=1,
        status=status,
        attempt=1,
        iteration_key="",
        input_json={},
        output_json={"ok": True} if status == WorkflowNodeRunStatus.SUCCEEDED.value else {},
        error_json=None,
        task_execution_id=task_execution_id,
        task_execution_ids=[],
        started_at=now,
        finished_at=now if status == WorkflowNodeRunStatus.SUCCEEDED.value else None,
        worker_task_id=worker_task_id,
        cancellation_requested=False,
    )
    node.created_at = now
    node.updated_at = now
    return node


class _FakeRuns:
    def __init__(self, run: WorkflowRun, nodes: list[WorkflowNodeRun]) -> None:
        self.run = run
        self.nodes = nodes

    async def get_run(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> WorkflowRun | None:
        if self.run.tenant_id == tenant_id and self.run.id == run_id:
            return self.run
        return None

    async def list_node_runs(
        self, tenant_id: uuid.UUID, workflow_run_id: uuid.UUID
    ) -> list[WorkflowNodeRun]:
        return list(self.nodes)


class _FakeEngine:
    def __init__(self, run: WorkflowRun, nodes: list[WorkflowNodeRun]) -> None:
        self.runs = _FakeRuns(run, nodes)
        self.db = MagicMock()

        async def _flush() -> None:
            return None

        async def _execute(*_a: Any, **_k: Any) -> None:
            return None

        async def _get(*_a: Any, **_k: Any) -> None:
            return None

        self.db.flush = _flush  # type: ignore[method-assign]
        self.db.execute = _execute  # type: ignore[method-assign]
        self.db.get = _get  # type: ignore[method-assign]


def test_request_celery_cancel_skips_inline() -> None:
    assert request_celery_cancel(None) is False
    assert request_celery_cancel("inline") is False


def test_request_celery_cancel_revokes_without_terminate() -> None:
    with patch("backend.workers.celery_app.celery_app") as app:
        assert request_celery_cancel("celery-abc") is True
        app.control.revoke.assert_called_once_with("celery-abc", terminate=False)


def test_should_abort_when_run_cancelled_or_flagged() -> None:
    run = _run(status=WorkflowRunStatus.CANCELLED.value)
    node = _node(run, node_id="n1", status=WorkflowNodeRunStatus.RUNNING.value)
    assert should_abort_node(node, run) is True
    run2 = _run()
    node2 = _node(run2, node_id="n2", status=WorkflowNodeRunStatus.RUNNING.value)
    node2.cancellation_requested = True
    assert should_abort_node(node2, run2) is True


def test_cancel_preserves_succeeded_and_flags_active() -> None:
    async def _case() -> None:
        run = _run()
        ok = _node(run, node_id="trigger", status=WorkflowNodeRunStatus.SUCCEEDED.value)
        active = _node(
            run,
            node_id="generate",
            status=WorkflowNodeRunStatus.RUNNING.value,
            worker_task_id="celery-1",
        )
        pending = _node(run, node_id="publish", status=WorkflowNodeRunStatus.PENDING.value)
        engine = _FakeEngine(run, [ok, active, pending])

        with patch(
            "backend.modules.workflows.workflow_cancellation.request_celery_cancel",
            return_value=True,
        ) as revoke:
            out = await cancel_run(engine, run.tenant_id, run.id)  # type: ignore[arg-type]

        assert out.status == WorkflowRunStatus.CANCELLED.value
        assert ok.status == WorkflowNodeRunStatus.SUCCEEDED.value
        assert ok.cancellation_requested is False
        assert active.status == WorkflowNodeRunStatus.CANCELLED.value
        assert active.cancellation_requested is True
        assert pending.status == WorkflowNodeRunStatus.CANCELLED.value
        revoke.assert_called_once_with("celery-1")

    asyncio.run(_case())


def test_cancel_rejects_succeeded_run() -> None:
    async def _case() -> None:
        run = _run(status=WorkflowRunStatus.SUCCEEDED.value)
        engine = _FakeEngine(run, [])
        with pytest.raises(HTTPException) as exc:
            await cancel_run(engine, run.tenant_id, run.id)  # type: ignore[arg-type]
        assert exc.value.status_code == 409

    asyncio.run(_case())


def test_finalize_keeps_cancelled_run_sticky() -> None:
    from backend.modules.workflows.engine_status import finalize_run_status

    run = _run(status=WorkflowRunStatus.CANCELLED.value)
    run.finished_at = datetime.now(timezone.utc)
    node = _node(run, node_id="x", status=WorkflowNodeRunStatus.FAILED.value)
    finalize_run_status(run, {node.node_id: node})
    assert run.status == WorkflowRunStatus.CANCELLED.value
