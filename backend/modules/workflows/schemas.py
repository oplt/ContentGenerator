"""Pydantic schemas for workflow node registry + definition APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from backend.modules.shared.schemas import ORMModel
from backend.modules.workflows.graph_schema import (
    CompileContext,
    DesignValidationContext,
    RuntimeClientContext,
    WorkflowGraph,
)


class NodePortResponse(BaseModel):
    name: str
    data_type: str
    required: bool = True
    description: str = ""


class RetryPolicyResponse(BaseModel):
    max_attempts: int
    backoff_seconds: float
    max_backoff_seconds: float = 300.0
    retry_on: list[str] = Field(default_factory=list)


class NodeDefinitionResponse(BaseModel):
    type: str
    version: int
    category: str
    display_name: str
    description: str
    implementation_status: str = "stable"
    executable: bool = True
    input_ports: list[NodePortResponse]
    output_ports: list[NodePortResponse]
    config_schema: dict[str, Any]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    required_capabilities: list[str]
    is_asynchronous: bool
    may_pause: bool
    retry_policy: RetryPolicyResponse


class NodeConfigValidateRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    version: int | None = None


class NodeConfigValidateResponse(BaseModel):
    valid: bool
    node_type: str
    version: int
    normalized_config: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)


class GraphValidateRequest(BaseModel):
    """Design-time graph validation. Hypothetical capability maps allowed."""

    graph: dict[str, Any] | WorkflowGraph = Field(default_factory=dict)
    context: DesignValidationContext | CompileContext | None = None


class GraphSimulateRequest(BaseModel):
    """Explicit design-time capability simulation (hypothetical caps OK)."""

    graph: dict[str, Any] | WorkflowGraph = Field(default_factory=dict)
    context: DesignValidationContext | None = None


class WorkflowDefinitionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = None


class WorkflowDraftSaveRequest(BaseModel):
    graph: WorkflowGraph
    input_schema_json: dict[str, Any] = Field(default_factory=dict)
    output_schema_json: dict[str, Any] = Field(default_factory=dict)


class WorkflowPublishRequest(BaseModel):
    version_id: UUID | None = None
    # Design-time compile check at publish; hypothetical caps allowed.
    context: DesignValidationContext | CompileContext | None = None


class WorkflowDefinitionResponse(ORMModel):
    id: UUID
    tenant_id: UUID
    name: str
    slug: str
    description: str | None
    status: str
    current_version_id: UUID | None
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class WorkflowVersionResponse(ORMModel):
    id: UUID
    tenant_id: UUID
    workflow_definition_id: UUID
    version: int
    graph_json: dict[str, Any]
    input_schema_json: dict[str, Any]
    output_schema_json: dict[str, Any]
    checksum: str | None
    published_at: datetime | None
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class WorkflowRunResponse(ORMModel):
    id: UUID
    tenant_id: UUID
    automation_id: UUID | None
    workflow_definition_id: UUID
    workflow_version_id: UUID
    brand_id: UUID | None
    trigger_type: str
    trigger_payload: dict[str, Any]
    status: str
    context_snapshot: dict[str, Any]
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    correlation_id: str | None
    created_at: datetime
    updated_at: datetime


class WorkflowNodeRunResponse(ORMModel):
    id: UUID
    tenant_id: UUID
    workflow_run_id: UUID
    node_id: str
    node_type: str
    node_version: int
    status: str
    attempt: int
    iteration_key: str = ""
    input_json: dict[str, Any]
    output_json: dict[str, Any]
    error_json: dict[str, Any] | None
    task_execution_id: UUID | None
    task_execution_ids: list[str]
    started_at: datetime | None
    finished_at: datetime | None
    waiting_reason: str | None
    resume_token: str | None
    claim_token: str | None = None
    claim_expires_at: datetime | None = None
    claimed_at: datetime | None = None
    worker_task_id: str | None = None
    next_attempt_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    execution_key: str | None = None
    last_error: str | None = None
    error_class: str | None = None
    cancellation_requested: bool = False
    created_at: datetime
    updated_at: datetime
    # Phase 15 inspection helpers (computed; tokens redacted on GET).
    duration_ms: int | None = None
    can_resume: bool = False
    can_retry: bool = False


class WorkflowRunInspectionMeta(BaseModel):
    version_number: int | None = None
    automation_name: str | None = None
    brand_name: str | None = None


class WorkflowRunDetailResponse(BaseModel):
    run: WorkflowRunResponse
    nodes: list[WorkflowNodeRunResponse]
    meta: WorkflowRunInspectionMeta | None = None


class WorkflowResumeNodeRequest(BaseModel):
    outcome: str = Field(
        default="received",
        pattern=r"^(approved|rejected|expired|elapsed|received)$",
    )
    decision: dict[str, Any] = Field(default_factory=dict)
    advance: bool = True


class WorkflowStartRunRequest(BaseModel):
    workflow_version_id: UUID | None = None
    trigger_payload: dict[str, Any] = Field(default_factory=dict)
    initial_inputs: dict[str, Any] = Field(default_factory=dict)
    automation_id: UUID | None = None
    brand_id: UUID | None = None
    correlation_id: str | None = Field(default=None, max_length=128)
    # Capability maps forbidden — server builds authoritative CompileContext.
    context: RuntimeClientContext | None = None
    advance: bool = True
    run_config: dict[str, Any] = Field(default_factory=dict)
    # Phase 15 — testing / dry-run controls (auth still required).
    dry_run: bool = False
    mock_generation: bool = False
    simulate_approval: bool = False


class WorkflowResumeRequest(BaseModel):
    resume_token: str | None = Field(default=None, min_length=8, max_length=128)
    event_key: str | None = Field(default=None, min_length=1, max_length=255)
    outcome: str = Field(
        default="received",
        pattern=r"^(approved|rejected|expired|elapsed|received)$",
    )
    decision: dict[str, Any] = Field(default_factory=dict)
    advance: bool = True

    @model_validator(mode="after")
    def _require_lookup(self) -> WorkflowResumeRequest:
        if not self.resume_token and not self.event_key:
            raise ValueError("resume_token or event_key is required")
        return self


class NodeTestRequest(BaseModel):
    version: int | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True
    mock_generation: bool = False
    brand_id: UUID | None = None
    context: RuntimeClientContext | None = None


class NodeTestResponse(BaseModel):
    node_type: str
    version: int
    status: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    waiting_reason: str | None = None
