"""Pydantic schemas for workflow node registry + definition APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from backend.modules.shared.schemas import ORMModel
from backend.modules.workflows.graph_schema import CompileContext, WorkflowGraph


class NodePortResponse(BaseModel):
    name: str
    data_type: str
    required: bool = True
    description: str = ""


class RetryPolicyResponse(BaseModel):
    max_attempts: int
    backoff_seconds: float
    retry_on: list[str] = Field(default_factory=list)


class NodeDefinitionResponse(BaseModel):
    type: str
    version: int
    category: str
    display_name: str
    description: str
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
    graph: dict[str, Any] | WorkflowGraph = Field(default_factory=dict)
    context: CompileContext | None = None


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
    context: CompileContext | None = None


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
    input_json: dict[str, Any]
    output_json: dict[str, Any]
    error_json: dict[str, Any] | None
    task_execution_id: UUID | None
    task_execution_ids: list[str]
    started_at: datetime | None
    finished_at: datetime | None
    waiting_reason: str | None
    resume_token: str | None
    created_at: datetime
    updated_at: datetime


class WorkflowRunDetailResponse(BaseModel):
    run: WorkflowRunResponse
    nodes: list[WorkflowNodeRunResponse]


class WorkflowStartRunRequest(BaseModel):
    workflow_version_id: UUID | None = None
    trigger_payload: dict[str, Any] = Field(default_factory=dict)
    initial_inputs: dict[str, Any] = Field(default_factory=dict)
    automation_id: UUID | None = None
    brand_id: UUID | None = None
    correlation_id: str | None = Field(default=None, max_length=128)
    context: CompileContext | None = None
    advance: bool = True
    run_config: dict[str, Any] = Field(default_factory=dict)
    # Phase 15 — testing / dry-run controls (auth still required).
    dry_run: bool = False
    mock_generation: bool = False
    simulate_approval: bool = False


class WorkflowResumeRequest(BaseModel):
    resume_token: str = Field(min_length=8, max_length=128)
    outcome: str = Field(
        pattern=r"^(approved|rejected|expired|elapsed|received)$"
    )
    decision: dict[str, Any] = Field(default_factory=dict)
    advance: bool = True


class NodeTestRequest(BaseModel):
    version: int | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True
    mock_generation: bool = False
    brand_id: UUID | None = None
    context: CompileContext | None = None


class NodeTestResponse(BaseModel):
    node_type: str
    version: int
    status: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    waiting_reason: str | None = None
