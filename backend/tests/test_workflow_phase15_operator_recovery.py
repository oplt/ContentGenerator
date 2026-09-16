"""Phase 15 — run inspection redaction + operator recovery."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.modules.workflows.operator_recovery import (
    cancel_run,
    retry_from_node,
    retry_node,
)
from backend.modules.workflows.payload_redact import redact_value
from backend.modules.workflows.run_inspection import serialize_node_run
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
)


def test_redact_value_masks_sensitive_keys() -> None:
    payload = {
        "prompt": "hello",
        "api_key": "sk-secret",
        "nested": {"refresh_token": "abc", "text": "ok"},
        "list": [{"password": "x"}, {"n": 1}],
    }
    out = redact_value(payload)
    assert out["prompt"] == "hello"
    assert out["api_key"] == "[redacted]"
    assert out["nested"]["refresh_token"] == "[redacted]"
    assert out["nested"]["text"] == "ok"
    assert out["list"][0]["password"] == "[redacted]"
    assert out["list"][1]["n"] == 1


def test_serialize_node_run_redacts_tokens_and_flags_actions() -> None:
    now = datetime.now(timezone.utc)
    node = WorkflowNodeRun(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        workflow_run_id=uuid.uuid4(),
        node_id="approval",
        node_type="approval",
        node_version=1,
        status=WorkflowNodeRunStatus.WAITING.value,
        attempt=1,
        iteration_key="",
        input_json={"oauth_token": "secret", "content_job_id": str(uuid.uuid4())},
        output_json={"approval_request_id": str(uuid.uuid4())},
        error_json=None,
        task_execution_ids=[],
        started_at=now - timedelta(seconds=2),
        finished_at=None,
        waiting_reason="approval_pending",
        resume_token="resume-secret-token",
        claim_token="claim-secret",
        cancellation_requested=False,
    )
    node.created_at = now
    node.updated_at = now
    payload = serialize_node_run(node)
    assert payload.resume_token is None
    assert payload.claim_token is None
    assert payload.input_json["oauth_token"] == "[redacted]"
    assert payload.can_resume is True
    assert payload.can_retry is False


def _run(*, status: str = WorkflowRunStatus.FAILED.value) -> WorkflowRun:
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
        finished_at=now if status == WorkflowRunStatus.FAILED.value else None,
        error_message="boom" if status == WorkflowRunStatus.FAILED.value else None,
    )
    run.created_at = now
    run.updated_at = now
    return run


def _node(
    run: WorkflowRun,
    *,
    node_id: str,
    status: str,
    node_type: str = "generate_text",
) -> WorkflowNodeRun:
    now = datetime.now(timezone.utc)
    node = WorkflowNodeRun(
        id=uuid.uuid4(),
        tenant_id=run.tenant_id,
        workflow_run_id=run.id,
        node_id=node_id,
        node_type=node_type,
        node_version=1,
        status=status,
        attempt=1,
        iteration_key="",
        input_json={},
        output_json={"text": "x"} if status == WorkflowNodeRunStatus.SUCCEEDED.value else {},
        error_json={"message": "fail"} if status == WorkflowNodeRunStatus.FAILED.value else None,
        task_execution_ids=[],
        started_at=now,
        finished_at=now,
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

        self.db.flush = _flush  # type: ignore[method-assign]
        self.versions = MagicMock()
        self._advanced = False

    async def advance(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> WorkflowRun:
        self._advanced = True
        return self.runs.run


def test_retry_node_rejects_succeeded() -> None:
    async def _case() -> None:
        run = _run()
        nodes = [
            _node(run, node_id="ok", status=WorkflowNodeRunStatus.SUCCEEDED.value),
            _node(run, node_id="bad", status=WorkflowNodeRunStatus.FAILED.value),
        ]
        engine = _FakeEngine(run, nodes)
        with pytest.raises(HTTPException) as exc:
            await retry_node(engine, run.tenant_id, run.id, "ok", advance=False)  # type: ignore[arg-type]
        assert exc.value.status_code == 409

    asyncio.run(_case())


def test_retry_node_reopens_failed() -> None:
    async def _run_case() -> None:
        run = _run()
        failed = _node(run, node_id="bad", status=WorkflowNodeRunStatus.FAILED.value)
        engine = _FakeEngine(run, [failed])
        out = await retry_node(engine, run.tenant_id, run.id, "bad", advance=True)  # type: ignore[arg-type]
        assert failed.status == WorkflowNodeRunStatus.READY.value
        assert failed.error_json is None
        assert run.status == WorkflowRunStatus.RUNNING.value
        assert engine._advanced is True
        assert out is run

    asyncio.run(_run_case())


def test_retry_from_resets_descendants_not_succeeded_ancestors() -> None:
    async def _run_case() -> None:
        run = _run()
        ok = _node(run, node_id="trigger", status=WorkflowNodeRunStatus.SUCCEEDED.value)
        bad = _node(run, node_id="generate", status=WorkflowNodeRunStatus.FAILED.value)
        downstream = _node(run, node_id="publish", status=WorkflowNodeRunStatus.PENDING.value)
        engine = _FakeEngine(run, [ok, bad, downstream])

        graph = {
            "nodes": [
                {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
                {"id": "generate", "type": "generate_text", "version": 1, "config": {}},
                {"id": "publish", "type": "publish", "version": 1, "config": {}},
            ],
            "edges": [
                {"source": "trigger", "target": "generate"},
                {"source": "generate", "target": "publish"},
            ],
        }
        version = MagicMock()
        version.graph_json = graph

        async def _get_version(*_a: Any, **_k: Any) -> Any:
            return version

        engine.versions.get_version = _get_version  # type: ignore[method-assign]

        await retry_from_node(engine, run.tenant_id, run.id, "generate", advance=False)  # type: ignore[arg-type]
        assert ok.status == WorkflowNodeRunStatus.SUCCEEDED.value
        assert bad.status == WorkflowNodeRunStatus.READY.value
        assert downstream.status == WorkflowNodeRunStatus.PENDING.value
        assert downstream.output_json == {}

    asyncio.run(_run_case())


def test_cancel_run_preserves_succeeded_nodes() -> None:
    async def _run_case() -> None:
        run = _run(status=WorkflowRunStatus.RUNNING.value)
        ok = _node(run, node_id="trigger", status=WorkflowNodeRunStatus.SUCCEEDED.value)
        waiting = _node(
            run,
            node_id="approval",
            status=WorkflowNodeRunStatus.WAITING.value,
            node_type="approval",
        )
        engine = _FakeEngine(run, [ok, waiting])

        async def _execute(*_a: Any, **_k: Any) -> None:
            return None

        engine.db.execute = _execute  # type: ignore[method-assign]

        out = await cancel_run(engine, run.tenant_id, run.id)  # type: ignore[arg-type]
        assert out.status == WorkflowRunStatus.CANCELLED.value
        assert ok.status == WorkflowNodeRunStatus.SUCCEEDED.value
        assert waiting.status == WorkflowNodeRunStatus.CANCELLED.value

    asyncio.run(_run_case())
