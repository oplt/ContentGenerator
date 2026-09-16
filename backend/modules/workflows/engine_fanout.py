"""Real item fan-out: spawn per-item WorkflowNodeRun iterations (Phase 4)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.engine_node_index import NodeRunIndex
from backend.modules.workflows.engine_ready import is_ready, successors
from backend.modules.workflows.graph_schema import WorkflowGraph
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
)


def iteration_key_for_item(item: Any, index: int) -> str:
    """Immutable-ish item key for WorkflowNodeRun.iteration_key (max 128)."""
    if isinstance(item, dict):
        for field in ("key", "id", "platform", "slug"):
            raw = item.get(field)
            if raw is not None and str(raw).strip():
                return str(raw).strip()[:128]
    if isinstance(item, UUID):
        return str(item)
    if isinstance(item, (str, int)):
        text = str(item).strip()
        if text:
            return text[:128]
    return f"i{index}"


def unique_iteration_keys(items: list[Any]) -> list[tuple[str, Any]]:
    """Return (key, item) pairs with de-duplicated keys (stable order)."""
    seen: dict[str, int] = {}
    out: list[tuple[str, Any]] = []
    for index, item in enumerate(items):
        base = iteration_key_for_item(item, index)
        count = seen.get(base, 0) + 1
        seen[base] = count
        key = base if count == 1 else f"{base}-{count}"[:128]
        out.append((key, item))
    return out


def _seed_iteration_inputs(
    *,
    item: Any,
    key: str,
    fan_out_node_id: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "item": item,
        "iteration_key": key,
        "fan_out_node_id": fan_out_node_id,
    }
    if isinstance(item, str):
        payload["text"] = item
    elif isinstance(item, dict):
        for field, value in item.items():
            payload.setdefault(str(field), value)
    return payload


async def materialize_fan_out_success(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    run: WorkflowRun,
    graph: WorkflowGraph,
    fan_out_node_id: str,
    output: dict[str, Any],
    node_runs: NodeRunIndex,
) -> list[WorkflowNodeRun]:
    """Replace successor placeholder with one READY row per fan-out item."""
    items = output.get("items")
    if not isinstance(items, list):
        items = []
    keyed = unique_iteration_keys(list(items))
    outs = successors(graph).get(fan_out_node_id, [])
    created: list[WorkflowNodeRun] = []
    now = datetime.now(timezone.utc)

    for edge in outs:
        target_id = edge.target
        graph_node = next((n for n in graph.nodes if n.id == target_id), None)
        if graph_node is None:
            continue
        placeholder = node_runs.get_iteration(target_id, "")
        if placeholder is not None and placeholder.status in {
            WorkflowNodeRunStatus.PENDING.value,
            WorkflowNodeRunStatus.READY.value,
            WorkflowNodeRunStatus.QUEUED.value,
        }:
            placeholder.status = WorkflowNodeRunStatus.SKIPPED.value
            placeholder.finished_at = now
            placeholder.waiting_reason = "superseded_by_fan_out"
            placeholder.error_json = None

        if not keyed:
            # No items: leave body skipped; try to unlock merge-style successors of body.
            for succ in successors(graph).get(target_id, []):
                target = node_runs.get(succ.target)
                if target is None:
                    continue
                if target.status == WorkflowNodeRunStatus.PENDING.value and is_ready(
                    succ.target, graph=graph, node_runs=node_runs
                ):
                    target.status = WorkflowNodeRunStatus.READY.value
            continue

        for key, item in keyed:
            existing = node_runs.get_iteration(target_id, key)
            if existing is not None:
                if existing.status == WorkflowNodeRunStatus.PENDING.value:
                    existing.status = WorkflowNodeRunStatus.READY.value
                    existing.input_json = {
                        **dict(existing.input_json or {}),
                        **_seed_iteration_inputs(
                            item=item,
                            key=key,
                            fan_out_node_id=fan_out_node_id,
                        ),
                    }
                created.append(existing)
                continue
            row = WorkflowNodeRun(
                tenant_id=tenant_id,
                workflow_run_id=run.id,
                node_id=target_id,
                node_type=graph_node.type,
                node_version=int(graph_node.version or 1),
                status=WorkflowNodeRunStatus.READY.value,
                iteration_key=key,
                input_json=_seed_iteration_inputs(
                    item=item,
                    key=key,
                    fan_out_node_id=fan_out_node_id,
                ),
            )
            db.add(row)
            node_runs.add(row)
            created.append(row)

    await db.flush()
    return created


async def ensure_downstream_iteration(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    run: WorkflowRun,
    graph: WorkflowGraph,
    source_node_id: str,
    iteration_key: str,
    output: dict[str, Any],
    node_runs: NodeRunIndex,
) -> list[str]:
    """Propagate an iteration to non-merge successors; unlock merge when ready."""
    if not iteration_key:
        return []
    unlocked: list[str] = []
    now = datetime.now(timezone.utc)
    for edge in successors(graph).get(source_node_id, []):
        target_id = edge.target
        graph_node = next((n for n in graph.nodes if n.id == target_id), None)
        if graph_node is None:
            continue
        target_primary = node_runs.get(target_id)
        if graph_node.type == "merge" or (
            target_primary is not None and target_primary.node_type == "merge"
        ):
            if target_primary is not None and target_primary.status == (
                WorkflowNodeRunStatus.PENDING.value
            ):
                if is_ready(target_id, graph=graph, node_runs=node_runs):
                    target_primary.status = WorkflowNodeRunStatus.READY.value
                    unlocked.append(target_id)
            continue

        existing = node_runs.get_iteration(target_id, iteration_key)
        if existing is not None:
            if existing.status == WorkflowNodeRunStatus.PENDING.value:
                existing.status = WorkflowNodeRunStatus.READY.value
                unlocked.append(target_id)
            continue

        # Skip blank placeholder once iterations exist.
        placeholder = node_runs.get_iteration(target_id, "")
        if placeholder is not None and placeholder.status in {
            WorkflowNodeRunStatus.PENDING.value,
            WorkflowNodeRunStatus.READY.value,
            WorkflowNodeRunStatus.QUEUED.value,
        }:
            placeholder.status = WorkflowNodeRunStatus.SKIPPED.value
            placeholder.finished_at = now
            placeholder.waiting_reason = "superseded_by_fan_out"

        row = WorkflowNodeRun(
            tenant_id=tenant_id,
            workflow_run_id=run.id,
            node_id=target_id,
            node_type=graph_node.type,
            node_version=int(graph_node.version or 1),
            status=WorkflowNodeRunStatus.READY.value,
            iteration_key=iteration_key,
            input_json={
                "iteration_key": iteration_key,
                "upstream": dict(output),
            },
        )
        db.add(row)
        node_runs.add(row)
        unlocked.append(target_id)
    await db.flush()
    return unlocked
