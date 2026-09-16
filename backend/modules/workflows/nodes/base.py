"""Workflow node contract: typed adapters around existing domain services."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, ClassVar, Generic, Type, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

ConfigT = TypeVar("ConfigT", bound=BaseModel)
InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class NodeResultStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    WAITING = "waiting"
    SKIPPED = "skipped"


class NodePort(BaseModel):
    name: str
    data_type: str
    required: bool = True
    description: str = ""


class RetryPolicyDefaults(BaseModel):
    max_attempts: int = Field(default=3, ge=1)
    backoff_seconds: float = Field(default=2.0, ge=0.0)
    retry_on: list[str] = Field(default_factory=lambda: ["transient"])


class NodeResult(BaseModel):
    status: NodeResultStatus
    output: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    waiting_reason: str | None = None


class EmptyModel(BaseModel):
    """Default empty I/O/config for stub or trigger nodes."""

    model_config = ConfigDict(extra="forbid")


class WorkflowNodeContext(BaseModel):
    """Runtime context passed into node execute(). No secrets."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tenant_id: UUID
    correlation_id: str | None = None
    workflow_run_id: UUID | None = None
    automation_id: UUID | None = None
    brand_id: UUID | None = None
    node_id: str | None = None
    node_run_id: UUID | None = None
    resume_token: str | None = None
    db: AsyncSession | None = None
    snapshot: dict[str, Any] = Field(default_factory=dict)


class WorkflowNodeNotFoundError(KeyError):
    """Raised when registry lookup fails for type/version."""


class WorkflowNodeNotImplementedError(RuntimeError):
    """Raised by stub nodes that are registered but not wired yet."""


class WorkflowNode(ABC, Generic[ConfigT, InputT, OutputT]):
    """Typed workflow node. Implementations wrap domain services — no business logic forks."""

    type: ClassVar[str]
    version: ClassVar[int] = 1
    category: ClassVar[str]
    display_name: ClassVar[str]
    description: ClassVar[str] = ""
    ConfigSchema: ClassVar[Type[BaseModel]] = EmptyModel
    InputSchema: ClassVar[Type[BaseModel]] = EmptyModel
    OutputSchema: ClassVar[Type[BaseModel]] = EmptyModel
    input_ports: ClassVar[list[NodePort]] = []
    output_ports: ClassVar[list[NodePort]] = []
    required_capabilities: ClassVar[list[str]] = []
    is_asynchronous: ClassVar[bool] = True
    may_pause: ClassVar[bool] = False
    retry_policy: ClassVar[RetryPolicyDefaults] = RetryPolicyDefaults()

    def validate_config(self, config: dict[str, Any] | BaseModel) -> BaseModel:
        if isinstance(config, self.ConfigSchema):
            return config
        return self.ConfigSchema.model_validate(config)

    def validate_inputs(self, inputs: dict[str, Any] | BaseModel) -> BaseModel:
        if isinstance(inputs, self.InputSchema):
            return inputs
        return self.InputSchema.model_validate(inputs)

    def validate_output(self, output: dict[str, Any] | BaseModel) -> BaseModel:
        if isinstance(output, self.OutputSchema):
            return output
        return self.OutputSchema.model_validate(output)

    @abstractmethod
    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        raise NotImplementedError


def make_stub_node(
    *,
    node_type: str,
    category: str,
    display_name: str,
    description: str,
    version: int = 1,
    may_pause: bool = False,
    required_capabilities: list[str] | None = None,
) -> Type[WorkflowNode[EmptyModel, EmptyModel, EmptyModel]]:
    """Factory for registered-but-unwired nodes (later phases)."""

    caps = list(required_capabilities or [])
    node_version = version
    node_category = category
    node_display_name = display_name
    node_description = description
    node_may_pause = may_pause

    class StubNode(WorkflowNode[EmptyModel, EmptyModel, EmptyModel]):
        type = node_type
        version = node_version
        category = node_category
        display_name = node_display_name
        description = node_description
        may_pause = node_may_pause
        required_capabilities = caps

        async def execute(
            self,
            context: WorkflowNodeContext,
            inputs: BaseModel,
            config: BaseModel,
        ) -> NodeResult:
            _ = (context, inputs, config)
            raise WorkflowNodeNotImplementedError(
                f"Node '{self.type}' v{self.version} is registered but not implemented yet"
            )

    StubNode.__name__ = "".join(part.title() for part in node_type.split("_")) + "Stub"
    StubNode.__qualname__ = StubNode.__name__
    return StubNode
