"""Canonical backend-owned workflow graph schema (DAG-as-data)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    type: str = Field(min_length=1, max_length=128)
    version: int = Field(default=1, ge=1)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "type")
    @classmethod
    def _strip_nonempty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must be non-empty")
        return cleaned


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=128)
    condition: str | None = None
    source_port: str | None = None
    target_port: str | None = None


class WorkflowGraph(BaseModel):
    """Persisted workflow graph format stored on WorkflowVersion.graph_json."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompileContext(BaseModel):
    """Optional runtime binding hints used during compile (not stored in graph)."""

    model_config = ConfigDict(extra="forbid")

    social_account_ids: list[UUID] = Field(default_factory=list)
    # account_id -> capability strings available on that account/platform
    account_capabilities: dict[str, list[str]] = Field(default_factory=dict)
    # account_id -> PlatformCapabilities.model_dump() (Phase 10 typed model)
    account_platform_capabilities: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # account_id -> provider/platform string id (for defaults when flags sparse)
    account_platforms: dict[str, str] = Field(default_factory=dict)
    require_publish_targets: bool = True
    allow_multiple_triggers: bool = False
    require_approval_before_publish: bool = True
    # When True, media nodes fail compile if account caps cannot be resolved.
    require_capability_check: bool = False
