"""Trigger nodes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.modules.workflows.nodes.base import (
    NodePort,
    NodeResult,
    NodeResultStatus,
    WorkflowNode,
    WorkflowNodeContext,
    make_stub_node,
)


class ManualTriggerConfig(BaseModel):
    label: str | None = None


class ManualTriggerInput(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class ManualTriggerOutput(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    trigger_type: str = "manual"


class ManualTriggerNode(WorkflowNode[ManualTriggerConfig, ManualTriggerInput, ManualTriggerOutput]):
    type = "manual_trigger"
    version = 1
    category = "triggers"
    display_name = "Manual Trigger"
    description = "Starts a workflow from an explicit operator or API invocation."
    ConfigSchema = ManualTriggerConfig
    InputSchema = ManualTriggerInput
    OutputSchema = ManualTriggerOutput
    is_asynchronous = False
    input_ports = [NodePort(name="payload", data_type="object", required=False)]
    output_ports = [
        NodePort(name="payload", data_type="object"),
        NodePort(name="trigger_type", data_type="string"),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        _ = (context, config)
        typed = ManualTriggerInput.model_validate(inputs.model_dump())
        output = ManualTriggerOutput(payload=dict(typed.payload), trigger_type="manual")
        return NodeResult(status=NodeResultStatus.SUCCEEDED, output=output.model_dump())


ScheduleTriggerNode = make_stub_node(
    node_type="schedule_trigger",
    category="triggers",
    display_name="Schedule Trigger",
    description="Starts a workflow from DB-backed schedule (Phase 7).",
)

WebhookTriggerNode = make_stub_node(
    node_type="webhook_trigger",
    category="triggers",
    display_name="Webhook Trigger",
    description="Starts a workflow from a validated external webhook callback.",
)
