"""Shared compiler result types."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowCompileError(BaseModel):
    code: str
    message: str
    node_id: str | None = None
    node_type: str | None = None


class WorkflowCompileResult(BaseModel):
    valid: bool
    errors: list[WorkflowCompileError] = Field(default_factory=list)
    normalized_graph: dict[str, object] | None = None
    checksum: str | None = None
