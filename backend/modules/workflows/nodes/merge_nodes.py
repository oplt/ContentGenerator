"""Fan-out (data) and Merge control nodes (Phase 12)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from backend.modules.workflows.nodes.base import (
    NodePort,
    NodeResult,
    NodeResultStatus,
    WorkflowNode,
    WorkflowNodeContext,
)


class FanOutConfig(BaseModel):
    mode: str = Field(default="list", pattern="^(list|account_ids)$")


class FanOutInput(BaseModel):
    items: list[Any] = Field(default_factory=list)
    social_account_ids: list[UUID] = Field(default_factory=list)


class FanOutOutput(BaseModel):
    items: list[Any]
    count: int
    mode: str
    # Graph-level parallel instances stay Phase 12+; this shapes a list for downstream.


class FanOutNode(WorkflowNode[FanOutConfig, FanOutInput, FanOutOutput]):
    type = "fan_out"
    version = 1
    category = "control"
    display_name = "Fan Out"
    description = (
        "Normalize items/account ids into a list for downstream nodes "
        "(data fan-out; parallel graph instances later)."
    )
    ConfigSchema = FanOutConfig
    InputSchema = FanOutInput
    OutputSchema = FanOutOutput
    input_ports = [
        NodePort(name="items", data_type="array", required=False),
        NodePort(name="social_account_ids", data_type="array", required=False),
    ]
    output_ports = [
        NodePort(name="items", data_type="array"),
        NodePort(name="count", data_type="number"),
        NodePort(name="mode", data_type="string"),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        _ = context
        typed_in = FanOutInput.model_validate(inputs.model_dump())
        typed_cfg = FanOutConfig.model_validate(config.model_dump())
        if typed_cfg.mode == "account_ids":
            items: list[Any] = [str(i) for i in typed_in.social_account_ids] or list(
                typed_in.items
            )
        else:
            items = list(typed_in.items)
            if not items and typed_in.social_account_ids:
                items = [str(i) for i in typed_in.social_account_ids]
        out = FanOutOutput(items=items, count=len(items), mode=typed_cfg.mode)
        return NodeResult(status=NodeResultStatus.SUCCEEDED, output=out.model_dump())


class MergeConfig(BaseModel):
    mode: str = Field(default="all", pattern="^(all|any)$")


class MergeInput(BaseModel):
    sources: list[dict[str, Any]] = Field(default_factory=list)
    bag: dict[str, Any] = Field(default_factory=dict)


class MergeOutput(BaseModel):
    merged: dict[str, Any]
    sources: list[dict[str, Any]]
    mode: str
    source_count: int


class MergeNode(WorkflowNode[MergeConfig, MergeInput, MergeOutput]):
    type = "merge"
    version = 1
    category = "control"
    display_name = "Merge"
    description = "Combine upstream branch outputs once predecessors are ready."
    ConfigSchema = MergeConfig
    InputSchema = MergeInput
    OutputSchema = MergeOutput
    input_ports = [
        NodePort(name="sources", data_type="array", required=False),
        NodePort(name="bag", data_type="object", required=False),
    ]
    output_ports = [
        NodePort(name="merged", data_type="object"),
        NodePort(name="sources", data_type="array"),
        NodePort(name="source_count", data_type="number"),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        _ = context
        typed_in = MergeInput.model_validate(inputs.model_dump())
        typed_cfg = MergeConfig.model_validate(config.model_dump())
        merged: dict[str, Any] = dict(typed_in.bag)
        sources = list(typed_in.sources)
        for row in sources:
            if isinstance(row, dict):
                merged.update(row)
        out = MergeOutput(
            merged=merged,
            sources=sources,
            mode=typed_cfg.mode,
            source_count=len(sources),
        )
        # Also expose merged keys at top-level for linear bag merge downstream.
        payload = out.model_dump()
        payload.update(merged)
        return NodeResult(status=NodeResultStatus.SUCCEEDED, output=payload)
