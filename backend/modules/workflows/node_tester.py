"""Single-node test execution (Phase 15)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.capability_context import build_runtime_compile_context
from backend.modules.workflows.context import build_node_context
from backend.modules.workflows.graph_schema import CompileContext, RuntimeClientContext
from backend.modules.workflows.nodes.base import WorkflowNodeNotFoundError
from backend.modules.workflows.registry import WorkflowNodeRegistry, get_default_registry
from backend.modules.workflows.runtime_bindings import authorize_runtime_bindings
from backend.modules.workflows.schemas import NodeTestResponse
from backend.modules.workflows.testing_support import (
    GENERATION_NODE_TYPES,
    mock_generation_result,
    simulated_approval_result,
)


class WorkflowNodeTester:
    def __init__(
        self,
        db: AsyncSession,
        *,
        registry: WorkflowNodeRegistry | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or get_default_registry()

    async def test_node(
        self,
        *,
        tenant_id: UUID,
        node_type: str,
        config: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        version: int | None = None,
        dry_run: bool = True,
        mock_generation: bool = False,
        brand_id: UUID | None = None,
        compile_context: CompileContext | RuntimeClientContext | None = None,
    ) -> NodeTestResponse:
        try:
            impl = self.registry.get(node_type, version)
        except WorkflowNodeNotFoundError as exc:
            return NodeTestResponse(
                node_type=node_type,
                version=version or 0,
                status="failed",
                inputs=dict(inputs or {}),
                config=dict(config or {}),
                error={"code": "unknown_node", "message": str(exc)},
            )

        cfg = dict(config or {})
        inp = dict(inputs or {})
        if dry_run and node_type == "publish":
            cfg["dry_run"] = True

        try:
            typed_cfg = impl.validate_config(cfg)
            typed_in = impl.validate_inputs(inp)
        except ValidationError as exc:
            return NodeTestResponse(
                node_type=impl.type,
                version=impl.version,
                status="failed",
                inputs=inp,
                config=cfg,
                error={
                    "code": "validation_error",
                    "message": "; ".join(e["msg"] for e in exc.errors()),
                },
            )

        normalized_cfg = typed_cfg.model_dump(mode="json")
        normalized_in = typed_in.model_dump(mode="json")

        if dry_run and node_type == "approval":
            result = simulated_approval_result(normalized_in)
            return NodeTestResponse(
                node_type=impl.type,
                version=impl.version,
                status=result.status.value,
                inputs=normalized_in,
                config=normalized_cfg,
                output=dict(result.output),
            )

        if mock_generation and node_type in GENERATION_NODE_TYPES:
            result = mock_generation_result(node_type, normalized_in)
            return NodeTestResponse(
                node_type=impl.type,
                version=impl.version,
                status=result.status.value,
                inputs=normalized_in,
                config=normalized_cfg,
                output=dict(result.output),
            )

        client_ids = list(compile_context.social_account_ids) if compile_context else []
        await authorize_runtime_bindings(
            self.db,
            tenant_id=tenant_id,
            brand_id=brand_id,
            social_account_ids=client_ids,
        )
        ctx = await build_runtime_compile_context(
            self.db,
            tenant_id=tenant_id,
            client=compile_context,
        )
        snapshot: dict[str, Any] = {
            "testing": {
                "dry_run": dry_run,
                "mock_generation": mock_generation,
                "simulate_approval": False,
                "single_node_test": True,
            },
            "compile_context": ctx.model_dump(mode="json") if ctx else {},
        }
        context = build_node_context(
            tenant_id=tenant_id,
            db=self.db,
            brand_id=brand_id,
            node_id=f"test:{impl.type}",
            snapshot=snapshot,
        )
        try:
            result = await impl.execute(context, typed_in, typed_cfg)
        except Exception as exc:  # noqa: BLE001 — surface to operator UI
            return NodeTestResponse(
                node_type=impl.type,
                version=impl.version,
                status="failed",
                inputs=normalized_in,
                config=normalized_cfg,
                error={"code": "execute_error", "message": str(exc)},
            )

        return NodeTestResponse(
            node_type=impl.type,
            version=impl.version,
            status=result.status.value,
            inputs=normalized_in,
            config=normalized_cfg,
            output=dict(result.output or {}),
            error=dict(result.error) if result.error else None,
            waiting_reason=result.waiting_reason,
        )
