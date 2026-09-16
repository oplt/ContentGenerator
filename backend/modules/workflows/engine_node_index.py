"""Index WorkflowNodeRun rows including fan-out iterations (Phase 4)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator
from typing import Any
from uuid import UUID

from backend.modules.workflows.run_models import WorkflowNodeRun


class NodeRunIndex:
    """Lookup by node_id (canonical) and by (node_id, iteration_key)."""

    def __init__(self, rows: Iterable[WorkflowNodeRun]) -> None:
        self.rows: list[WorkflowNodeRun] = list(rows)
        self.by_uuid: dict[UUID, WorkflowNodeRun] = {}
        self._by_node: dict[str, list[WorkflowNodeRun]] = defaultdict(list)
        for row in self.rows:
            self.by_uuid[row.id] = row
            self._by_node[row.node_id].append(row)
        for lst in self._by_node.values():
            lst.sort(key=lambda r: ((r.iteration_key or ""), str(r.id)))

    def add(self, row: WorkflowNodeRun) -> None:
        self.rows.append(row)
        self.by_uuid[row.id] = row
        bucket = self._by_node[row.node_id]
        bucket.append(row)
        bucket.sort(key=lambda r: ((r.iteration_key or ""), str(r.id)))

    def get(self, node_id: str, default: Any = None) -> WorkflowNodeRun | Any:
        try:
            return self[node_id]
        except KeyError:
            return default

    def get_iteration(self, node_id: str, iteration_key: str = "") -> WorkflowNodeRun | None:
        key = iteration_key or ""
        for row in self._by_node.get(node_id, []):
            if (row.iteration_key or "") == key:
                return row
        return None

    def iterations(
        self,
        node_id: str,
        *,
        include_placeholder: bool = False,
    ) -> list[WorkflowNodeRun]:
        """Stable-ordered iterations. Prefer real keys when present."""
        rows = list(self._by_node.get(node_id, []))
        real = [r for r in rows if (r.iteration_key or "")]
        if real and not include_placeholder:
            return real
        if include_placeholder:
            return rows
        return [r for r in rows if not (r.iteration_key or "")]

    def __getitem__(self, node_id: str) -> WorkflowNodeRun:
        rows = self._by_node.get(node_id) or []
        if not rows:
            raise KeyError(node_id)
        for row in rows:
            if not (row.iteration_key or ""):
                return row
        return rows[0]

    def __contains__(self, node_id: object) -> bool:
        return isinstance(node_id, str) and node_id in self._by_node

    def __iter__(self) -> Iterator[str]:
        return iter(self._by_node)

    def values(self) -> list[WorkflowNodeRun]:
        return list(self.rows)

    def items(self) -> list[tuple[str, WorkflowNodeRun]]:
        return [(node_id, self[node_id]) for node_id in self._by_node]


def output_storage_key(node_id: str, iteration_key: str | None) -> str:
    key = (iteration_key or "").strip()
    return f"{node_id}#{key}" if key else node_id


def collect_upstream_outputs(
    predecessor_ids: list[str],
    node_outputs: dict[str, Any],
    node_runs: NodeRunIndex,
) -> list[dict[str, Any]]:
    """Collect predecessor outputs; expand fan-out iterations in stable key order."""
    upstream: list[dict[str, Any]] = []
    for pid in predecessor_ids:
        iters = node_runs.iterations(pid)
        if len(iters) > 1 or (iters and (iters[0].iteration_key or "")):
            for row in iters:
                stored = node_outputs.get(output_storage_key(pid, row.iteration_key))
                if isinstance(stored, dict):
                    upstream.append(dict(stored))
                elif isinstance(row.output_json, dict) and row.output_json:
                    upstream.append(dict(row.output_json))
            continue
        raw = node_outputs.get(pid)
        if isinstance(raw, dict):
            upstream.append(dict(raw))
    return upstream
