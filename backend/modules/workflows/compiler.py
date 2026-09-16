"""Workflow graph compiler — validate before publish/execute."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from backend.modules.workflows.compiler_checks import (
    detect_cycles,
    find_duplicate_node_ids,
    find_unreachable,
    validate_edges,
    validate_port_compatibility,
)
from backend.modules.workflows.compiler_control import validate_control_flow
from backend.modules.workflows.compiler_semantics import (
    collect_trigger_errors,
    graph_checksum,
    validate_approval_placement,
    validate_capabilities,
    validate_publish_targets,
)
from backend.modules.workflows.compiler_types import (
    WorkflowCompileError,
    WorkflowCompileResult,
)
from backend.modules.workflows.graph_schema import CompileContext, WorkflowGraph
from backend.modules.workflows.nodes.base import WorkflowNode, WorkflowNodeNotFoundError
from backend.modules.workflows.registry import WorkflowNodeRegistry, get_default_registry

# Re-export for existing imports.
__all__ = [
    "WorkflowCompileError",
    "WorkflowCompileResult",
    "WorkflowCompiler",
]


class WorkflowCompiler:
    """Validate canonical workflow graphs. Invalid graphs must not be published/run."""

    def __init__(self, registry: WorkflowNodeRegistry | None = None) -> None:
        self.registry = registry or get_default_registry()

    def validate_graph(
        self,
        graph: dict[str, Any] | WorkflowGraph,
        context: CompileContext | dict[str, Any] | None = None,
    ) -> WorkflowCompileResult:
        errors: list[WorkflowCompileError] = []
        try:
            parsed = (
                graph
                if isinstance(graph, WorkflowGraph)
                else WorkflowGraph.model_validate(graph)
            )
        except ValidationError as exc:
            return WorkflowCompileResult(
                valid=False,
                errors=[
                    WorkflowCompileError(code="invalid_graph", message=err["msg"])
                    for err in exc.errors()
                ],
            )

        compile_ctx = (
            context
            if isinstance(context, CompileContext)
            else CompileContext.model_validate(context or {})
        )

        errors.extend(find_duplicate_node_ids(parsed.nodes))
        node_ids = {node.id for node in parsed.nodes}
        errors.extend(validate_edges(parsed, node_ids))

        resolved: dict[str, WorkflowNode[Any, Any, Any]] = {}
        for node in parsed.nodes:
            if node.id not in node_ids:
                continue
            try:
                impl = self.registry.get(node.type, node.version)
            except WorkflowNodeNotFoundError as exc:
                errors.append(
                    WorkflowCompileError(
                        code="unknown_node_type",
                        message=str(exc),
                        node_id=node.id,
                        node_type=node.type,
                    )
                )
                continue
            resolved[node.id] = impl
            try:
                impl.validate_config(node.config)
            except ValidationError as exc:
                errors.append(
                    WorkflowCompileError(
                        code="invalid_config",
                        message="; ".join(err["msg"] for err in exc.errors()),
                        node_id=node.id,
                        node_type=node.type,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    WorkflowCompileError(
                        code="invalid_config",
                        message=str(exc),
                        node_id=node.id,
                        node_type=node.type,
                    )
                )

        # Structural DAG checks use declared edges even when some nodes failed resolve.
        errors.extend(detect_cycles(node_ids, parsed.edges))
        triggers, trigger_errors = collect_trigger_errors(
            resolved,
            parsed.edges,
            allow_multiple=compile_ctx.allow_multiple_triggers,
        )
        errors.extend(trigger_errors)
        errors.extend(find_unreachable(node_ids, parsed.edges, triggers))
        errors.extend(validate_port_compatibility(parsed.edges, resolved))
        errors.extend(
            validate_approval_placement(
                resolved,
                parsed.edges,
                require_before_publish=compile_ctx.require_approval_before_publish,
            )
        )
        errors.extend(validate_publish_targets(resolved, compile_ctx))
        errors.extend(validate_capabilities(resolved, compile_ctx))
        errors.extend(validate_control_flow(parsed, resolved))

        valid = not errors
        return WorkflowCompileResult(
            valid=valid,
            errors=errors,
            normalized_graph=parsed.model_dump(mode="json") if valid else None,
            checksum=graph_checksum(parsed) if valid else None,
        )
