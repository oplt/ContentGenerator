"""Delay and Wait control nodes — durable pause without holding workers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

from pydantic import BaseModel, Field, model_validator

from backend.modules.workflows.nodes.base import (
    NodePort,
    NodeResult,
    NodeResultStatus,
    WorkflowNode,
    WorkflowNodeContext,
)


class DelayConfig(BaseModel):
    duration_seconds: int | None = Field(default=60, ge=1, le=604_800)
    until: datetime | None = None

    @model_validator(mode="after")
    def _one_schedule(self) -> DelayConfig:
        if self.until is not None:
            return self
        if self.duration_seconds is None:
            raise ValueError("delay requires duration_seconds or until")
        return self


class DelayInput(BaseModel):
    pass


class DelayOutput(BaseModel):
    resume_at: datetime
    scheduled: bool = True
    status: str = "pending"


class DelayNode(WorkflowNode[DelayConfig, DelayInput, DelayOutput]):
    type = "delay"
    version = 1
    category = "control"
    display_name = "Delay"
    description = "Pause until a duration/date; Postgres owns wake_at (Celery is optional fast wake)."
    ConfigSchema = DelayConfig
    InputSchema = DelayInput
    OutputSchema = DelayOutput
    may_pause = True
    input_ports: ClassVar[list[NodePort]] = []
    output_ports = [
        NodePort(name="resume_at", data_type="string"),
        NodePort(name="scheduled", data_type="boolean"),
        NodePort(name="status", data_type="string"),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        _ = inputs
        typed_cfg = DelayConfig.model_validate(config.model_dump())
        now = datetime.now(timezone.utc)
        if typed_cfg.until is not None:
            resume_at = typed_cfg.until
            if resume_at.tzinfo is None:
                resume_at = resume_at.replace(tzinfo=timezone.utc)
        else:
            resume_at = now + timedelta(seconds=int(typed_cfg.duration_seconds or 1))
        out = DelayOutput(resume_at=resume_at, scheduled=True, status="pending")
        return NodeResult(
            status=NodeResultStatus.WAITING,
            output=out.model_dump(mode="json"),
            waiting_reason="delay_until",
        )


class WaitConfig(BaseModel):
    event: str = Field(default="manual", pattern="^(manual|webhook)$")
    timeout_seconds: int | None = Field(default=None, ge=60, le=604_800)
    on_timeout: str = Field(default="fail", pattern="^(fail|continue)$")


class WaitInput(BaseModel):
    correlation_key: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class WaitOutput(BaseModel):
    status: str = "pending"
    event: str
    correlation_key: str | None = None
    event_payload: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int | None = None
    on_timeout: str | None = None


class WaitNode(WorkflowNode[WaitConfig, WaitInput, WaitOutput]):
    type = "wait"
    version = 1
    category = "control"
    display_name = "Wait For Event"
    description = "Pause until webhook/manual resume; optional Postgres-owned timeout."
    ConfigSchema = WaitConfig
    InputSchema = WaitInput
    OutputSchema = WaitOutput
    may_pause = True
    input_ports = [
        NodePort(name="correlation_key", data_type="string", required=False),
        NodePort(name="payload", data_type="object", required=False),
    ]
    output_ports = [
        NodePort(name="status", data_type="string"),
        NodePort(name="event", data_type="string"),
        NodePort(name="event_payload", data_type="object", required=False),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        _ = context
        typed_in = WaitInput.model_validate(inputs.model_dump())
        typed_cfg = WaitConfig.model_validate(config.model_dump())
        out = WaitOutput(
            status="pending",
            event=typed_cfg.event,
            correlation_key=typed_in.correlation_key,
            event_payload=dict(typed_in.payload),
            timeout_seconds=typed_cfg.timeout_seconds,
            on_timeout=typed_cfg.on_timeout if typed_cfg.timeout_seconds else None,
        )
        return NodeResult(
            status=NodeResultStatus.WAITING,
            output=out.model_dump(mode="json"),
            waiting_reason="event_pending",
        )
