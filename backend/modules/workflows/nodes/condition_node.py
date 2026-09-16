"""Condition node — evaluate bag field and emit branch label (Phase 12)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.workflows.nodes.base import (
    NodePort,
    NodeResult,
    NodeResultStatus,
    WorkflowNode,
    WorkflowNodeContext,
)


class ConditionConfig(BaseModel):
    field: str = "value"
    operator: str = Field(
        default="truthy",
        pattern="^(truthy|eq|neq|gt|gte|lt|lte)$",
    )
    compare_to: Any | None = None
    true_branch: str = "true"
    false_branch: str = "false"


class ConditionInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    value: Any | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ConditionOutput(BaseModel):
    branch: str
    matched: bool
    evaluated_value: Any | None = None
    field: str


class ConditionNode(WorkflowNode[ConditionConfig, ConditionInput, ConditionOutput]):
    type = "condition"
    version = 1
    category = "control"
    display_name = "Condition"
    description = "Branch on a field comparison; edge.condition must match output.branch."
    ConfigSchema = ConditionConfig
    InputSchema = ConditionInput
    OutputSchema = ConditionOutput
    input_ports = [
        NodePort(name="value", data_type="any", required=False),
        NodePort(name="payload", data_type="object", required=False),
    ]
    output_ports = [
        NodePort(name="branch", data_type="string"),
        NodePort(name="matched", data_type="boolean"),
        NodePort(name="evaluated_value", data_type="any", required=False),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        _ = context
        typed_in = ConditionInput.model_validate(inputs.model_dump())
        typed_cfg = ConditionConfig.model_validate(config.model_dump())
        bag = dict(typed_in.payload)
        raw = inputs.model_dump()
        bag.update({k: v for k, v in raw.items() if k not in {"payload"}})
        evaluated = bag.get(typed_cfg.field, typed_in.value)
        matched = _eval(evaluated, typed_cfg.operator, typed_cfg.compare_to)
        branch = typed_cfg.true_branch if matched else typed_cfg.false_branch
        out = ConditionOutput(
            branch=branch,
            matched=matched,
            evaluated_value=evaluated,
            field=typed_cfg.field,
        )
        return NodeResult(status=NodeResultStatus.SUCCEEDED, output=out.model_dump())


def _eval(value: Any, operator: str, compare_to: Any) -> bool:
    if operator == "truthy":
        return bool(value)
    if operator == "eq":
        return bool(value == compare_to)
    if operator == "neq":
        return bool(value != compare_to)
    try:
        left = float(value)
        right = float(compare_to)
    except (TypeError, ValueError):
        return False
    if operator == "gt":
        return left > right
    if operator == "gte":
        return left >= right
    if operator == "lt":
        return left < right
    if operator == "lte":
        return left <= right
    return False
