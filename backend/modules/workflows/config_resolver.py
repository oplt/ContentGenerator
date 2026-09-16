"""Deterministic workflow configuration resolution (Phase 8).

Precedence (later wins):
  node defaults → workflow node.config → brand/profile → automation
  → social-account overrides → explicit run/trigger params

Resolved configs are frozen into WorkflowRun.context_snapshot at start_run.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.modules.workflows import config_layers as layers
from backend.modules.workflows import config_snapshots as snapshots
from backend.modules.workflows.config_merge import (
    apply_key_aliases,
    as_mapping,
    deep_merge,
    pick_allowed_keys,
    strip_secrets,
)
from backend.modules.workflows.graph_schema import CompileContext, WorkflowGraph
from backend.modules.workflows.registry import WorkflowNodeRegistry, get_default_registry

PRECEDENCE = (
    "node_defaults",
    "workflow_node_config",
    "brand_profile",
    "automation",
    "social_account",
    "run_params",
)


class ConfigResolver:
    def __init__(
        self,
        db: AsyncSession,
        *,
        registry: WorkflowNodeRegistry | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or get_default_registry()

    async def build_snapshot(
        self,
        *,
        tenant_id: UUID,
        graph: WorkflowGraph,
        graph_checksum: str | None,
        brand_id: UUID | None = None,
        automation_id: UUID | None = None,
        compile_context: CompileContext | None = None,
        trigger_payload: dict[str, Any] | None = None,
        initial_inputs: dict[str, Any] | None = None,
        run_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        trigger_payload = dict(trigger_payload or {})
        initial_inputs = dict(initial_inputs or {})
        run_config = dict(run_config or {})

        automation = await layers.load_automation(self.db, tenant_id, automation_id)
        if automation is not None and brand_id is None:
            brand_id = automation.brand_id

        brand = await layers.load_brand(self.db, tenant_id, brand_id)
        profile = await layers.load_profile(self.db, tenant_id, brand_id)
        targets, accounts, bsa_by_account = await layers.load_targets_and_accounts(
            self.db,
            tenant_id=tenant_id,
            automation=automation,
            brand_id=brand_id,
            compile_context=compile_context,
        )

        brand_cfg = layers.brand_layer(brand, profile)
        automation_cfg, automation_node_overrides = layers.automation_layers(automation)
        account_cfg, account_node_overrides = layers.account_layers(
            targets, accounts, bsa_by_account
        )
        run_cfg = layers.run_layer(initial_inputs, trigger_payload, run_config)

        resolved_node_configs: dict[str, dict[str, Any]] = {}
        for node in graph.nodes:
            resolved_node_configs[node.id] = self.resolve_node_config(
                node_type=node.type,
                node_version=node.version,
                graph_config=dict(node.config or {}),
                brand_layer=brand_cfg,
                automation_layer=automation_cfg,
                automation_node_overrides=as_mapping(automation_node_overrides.get(node.id)),
                account_layer=account_cfg,
                account_node_overrides=as_mapping(account_node_overrides.get(node.id)),
                run_layer=run_cfg,
            )

        return {
            "initial_inputs": strip_secrets(initial_inputs),
            "compile_context": (
                compile_context.model_dump(mode="json") if compile_context else {}
            ),
            "node_outputs": {},
            "graph_checksum": graph_checksum,
            "config_precedence": list(PRECEDENCE),
            "brand": snapshots.brand_snapshot(brand),
            "brand_profile": snapshots.profile_snapshot(profile),
            "automation": snapshots.automation_snapshot(automation),
            "accounts": snapshots.accounts_snapshot(accounts, bsa_by_account, targets),
            "resolved_editorial": strip_secrets(brand_cfg),
            "resolved_node_configs": resolved_node_configs,
            "providers": {
                "llm": settings.LLM_PROVIDER,
                "llm_model": settings.LLM_MODEL,
            },
            "run_params": strip_secrets(run_cfg),
        }

    def resolve_node_config(
        self,
        *,
        node_type: str,
        node_version: int,
        graph_config: dict[str, Any],
        brand_layer: dict[str, Any],
        automation_layer: dict[str, Any],
        automation_node_overrides: dict[str, Any],
        account_layer: dict[str, Any],
        account_node_overrides: dict[str, Any],
        run_layer: dict[str, Any],
    ) -> dict[str, Any]:
        impl = self.registry.get(node_type, node_version)
        defaults = impl.ConfigSchema().model_dump()
        allowed = set(impl.ConfigSchema.model_fields.keys())
        merged = deep_merge(
            defaults,
            apply_key_aliases(graph_config),
            apply_key_aliases(brand_layer),
            apply_key_aliases(automation_layer),
            apply_key_aliases(automation_node_overrides),
            apply_key_aliases(account_layer),
            apply_key_aliases(account_node_overrides),
            apply_key_aliases(run_layer),
        )
        filtered = pick_allowed_keys(merged, allowed)
        return impl.validate_config(filtered).model_dump(mode="json")
