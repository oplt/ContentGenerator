"""Semantic compile rules: triggers, approval placement, publish targets, caps."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from backend.modules.publishing.platform_capabilities import (
    MEDIA_CAPABILITIES,
    PlatformCapabilities,
    platform_defaults,
    workflow_capability_tags,
)
from backend.modules.workflows.capability_context import enrich_compile_context
from backend.modules.workflows.compiler_types import WorkflowCompileError
from backend.modules.workflows.graph_schema import CompileContext, GraphEdge, WorkflowGraph
from backend.modules.workflows.nodes.base import WorkflowNode

# Product/runtime tags — not inferred from SocialAccount.capability_flags alone.
_SOFT_CAPABILITIES = frozenset({"chess"})


def is_trigger(node: WorkflowNode[Any, Any, Any]) -> bool:
    return node.category == "triggers" or node.type.endswith("_trigger")


def collect_trigger_errors(
    resolved: dict[str, WorkflowNode[Any, Any, Any]],
    edges: list[GraphEdge],
    *,
    allow_multiple: bool,
) -> tuple[set[str], list[WorkflowCompileError]]:
    errors: list[WorkflowCompileError] = []
    triggers = {node_id for node_id, node in resolved.items() if is_trigger(node)}
    indegree: dict[str, int] = defaultdict(int)
    for edge in edges:
        indegree[edge.target] += 1

    for node_id in triggers:
        if indegree.get(node_id, 0) > 0:
            errors.append(
                WorkflowCompileError(
                    code="trigger_has_incoming_edge",
                    message=f"trigger '{node_id}' must not have incoming edges",
                    node_id=node_id,
                    node_type=resolved[node_id].type,
                )
            )

    if not triggers:
        errors.append(
            WorkflowCompileError(
                code="missing_trigger",
                message="workflow must include at least one trigger node",
            )
        )
    elif len(triggers) > 1 and not allow_multiple:
        errors.append(
            WorkflowCompileError(
                code="multiple_triggers",
                message=(
                    "multiple trigger roots are not allowed "
                    f"({', '.join(sorted(triggers))})"
                ),
            )
        )
    return triggers, errors


def validate_approval_placement(
    resolved: dict[str, WorkflowNode[Any, Any, Any]],
    edges: list[GraphEdge],
    *,
    require_before_publish: bool,
) -> list[WorkflowCompileError]:
    approvals = {nid for nid, n in resolved.items() if n.type == "approval"}
    publishes = {nid for nid, n in resolved.items() if n.type == "publish"}
    if not approvals or not publishes:
        return []

    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.source].append(edge.target)

    errors: list[WorkflowCompileError] = []
    for publish_id in publishes:
        for approval_id in approvals:
            if _reachable(adjacency, publish_id, approval_id):
                errors.append(
                    WorkflowCompileError(
                        code="approval_after_publish",
                        message=(
                            f"approval '{approval_id}' is downstream of publish "
                            f"'{publish_id}'"
                        ),
                        node_id=approval_id,
                        node_type="approval",
                    )
                )
            elif require_before_publish and not _reachable(adjacency, approval_id, publish_id):
                errors.append(
                    WorkflowCompileError(
                        code="approval_not_before_publish",
                        message=(
                            f"approval '{approval_id}' must precede publish "
                            f"'{publish_id}' on some path"
                        ),
                        node_id=approval_id,
                        node_type="approval",
                    )
                )
    return errors


def validate_publish_targets(
    resolved: dict[str, WorkflowNode[Any, Any, Any]],
    context: CompileContext,
) -> list[WorkflowCompileError]:
    if not any(n.type == "publish" for n in resolved.values()):
        return []
    if not context.require_publish_targets:
        return []
    if context.social_account_ids:
        return []
    return [
        WorkflowCompileError(
            code="missing_publish_targets",
            message="Publish node requires one or more social_account_ids in compile context",
            node_type="publish",
        )
    ]


def validate_capabilities(
    resolved: dict[str, WorkflowNode[Any, Any, Any]],
    context: CompileContext,
) -> list[WorkflowCompileError]:
    if not context.social_account_ids:
        return []

    ctx = enrich_compile_context(context)
    available = _available_capability_tags(ctx)
    has_media_nodes = any(
        MEDIA_CAPABILITIES.intersection(_hard_required(n.required_capabilities))
        for n in resolved.values()
    )

    if not available:
        if not (ctx.require_capability_check or has_media_nodes):
            # Draft / unbound — soft-skip non-media when caps unresolved.
            return []
        return [
            WorkflowCompileError(
                code="unknown_capabilities",
                message=(
                    "selected accounts have unresolved platform capabilities; "
                    "cannot validate media/runtime requirements"
                ),
            )
        ]

    errors: list[WorkflowCompileError] = []
    for node_id, node in resolved.items():
        required = _hard_required(node.required_capabilities)
        missing = [cap for cap in required if cap not in available]
        if missing:
            errors.append(
                WorkflowCompileError(
                    code="incompatible_capabilities",
                    message=(
                        f"node '{node_id}' requires capabilities {missing} "
                        "not provided by selected accounts"
                    ),
                    node_id=node_id,
                    node_type=node.type,
                )
            )
    return errors


def _hard_required(caps: list[str]) -> list[str]:
    return [c for c in caps if c not in _SOFT_CAPABILITIES]


def _available_capability_tags(context: CompileContext) -> set[str]:
    available: set[str] = set()
    for account_id in context.social_account_ids:
        key = str(account_id)
        tags = context.account_capabilities.get(key) or []
        if tags:
            available.update(tags)
            continue
        typed = context.account_platform_capabilities.get(key)
        if isinstance(typed, dict) and typed:
            caps = PlatformCapabilities.model_validate(typed)
            available.update(workflow_capability_tags(caps))
            continue
        platform = context.account_platforms.get(key)
        if platform:
            available.update(workflow_capability_tags(platform_defaults(platform)))
    return available


def _reachable(adjacency: dict[str, list[str]], start: str, goal: str) -> bool:
    if start == goal:
        return True
    seen: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        for nxt in adjacency.get(current, []):
            if nxt == goal:
                return True
            if nxt not in seen:
                queue.append(nxt)
    return False


def graph_checksum(graph: WorkflowGraph) -> str:
    import hashlib
    import json

    payload = graph.model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
