"""Shared bag merge helpers for workflow input resolution."""

from __future__ import annotations

from typing import Any


def merge_upstream_bag(
    *,
    trigger_payload: dict[str, Any],
    initial_inputs: dict[str, Any],
    upstream_outputs: list[dict[str, Any]],
) -> dict[str, Any]:
    bag: dict[str, Any] = {}
    bag.update(initial_inputs)
    bag.update(trigger_payload)
    payload = trigger_payload.get("payload")
    if isinstance(payload, dict):
        bag.update(payload)
    for output in upstream_outputs:
        if isinstance(output, dict):
            bag.update(output)
    return bag


def lookup_dotted(data: Any, path: str | None) -> Any:
    """Simple dotted-path lookup. No expression language."""
    if path is None or path == "":
        return data
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current
