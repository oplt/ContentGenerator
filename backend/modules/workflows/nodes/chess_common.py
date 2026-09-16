"""Shared helpers for chess workflow nodes."""

from __future__ import annotations

from pydantic import BaseModel

from backend.modules.workflows.nodes.base import NodeResult, NodeResultStatus


def ok(payload: BaseModel) -> NodeResult:
    return NodeResult(status=NodeResultStatus.SUCCEEDED, output=payload.model_dump(mode="json"))
