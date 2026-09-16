"""Recover WorkflowNodeRun rows stranded after worker crash / expired claim lease."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.modules.workflows.node_retry import (
    ErrorClass,
    next_attempt_at_for,
    should_retry,
)
from backend.modules.workflows.registry import get_default_registry
from backend.modules.workflows import run_repository as node_claims


async def recover_stale_workflow_node_runs(
    db: AsyncSession,
    *,
    batch_size: int | None = None,
    enqueue_advance: bool = True,
) -> list[dict[str, Any]]:
    """Requeue or fail RUNNING/QUEUED nodes whose claim lease expired."""
    registry = get_default_registry()
    stale = await node_claims.list_stale_claimed_nodes(db, batch_size=batch_size)
    results: list[dict[str, Any]] = []
    advance_targets: set[tuple[str, str]] = set()

    for node in stale:
        try:
            impl = registry.get(node.node_type, int(node.node_version or 1))
            policy = impl.retry_policy
        except Exception:  # noqa: BLE001 — unknown type → fail closed
            from backend.modules.workflows.nodes.base import RetryPolicyDefaults

            policy = RetryPolicyDefaults(max_attempts=1)

        attempt = int(node.attempt or 0)
        tenant_id = node.tenant_id
        run_id = node.workflow_run_id
        error_class = ErrorClass.TRANSIENT.value
        message = "Worker claim lease expired"

        if should_retry(error_class=error_class, attempt=attempt, policy=policy):
            next_at = next_attempt_at_for(attempt, policy)
            released = await node_claims.release_node_claim(
                db,
                tenant_id=tenant_id,
                node_run_id=node.id,
                claim_token=node.claim_token,
                requeue=True,
                next_attempt_at=next_at,
            )
            if released is not None:
                released.last_error = message
                released.error_class = error_class
                released.error_json = {
                    "code": "claim_lease_expired",
                    "message": message,
                    "error_class": error_class,
                    "attempt": attempt,
                }
            action = "requeued" if released else "release_missed"
            if released is not None:
                advance_targets.add((str(tenant_id), str(run_id)))
        else:
            failed = await node_claims.fail_node(
                db,
                tenant_id=tenant_id,
                node_run_id=node.id,
                claim_token=node.claim_token,
                error={
                    "code": "claim_lease_expired",
                    "message": "Worker claim lease expired after max attempts",
                    "attempt": attempt,
                    "max_attempts": int(policy.max_attempts),
                    "error_class": error_class,
                },
                error_class=error_class,
                last_error=message,
            )
            action = "failed" if failed else "fail_missed"
            if failed is not None:
                advance_targets.add((str(tenant_id), str(run_id)))

        results.append(
            {
                "node_run_id": str(node.id),
                "workflow_run_id": str(run_id),
                "tenant_id": str(tenant_id),
                "action": action,
                "attempt": attempt,
                "max_attempts": int(policy.max_attempts),
            }
        )
        from backend.modules.workflows.observability import (
            record_node_claim_expiration,
            record_node_stale_recovery,
        )

        record_node_claim_expiration(node_type=node.node_type)
        if action in {"requeued", "failed"}:
            record_node_stale_recovery(action=action, node_type=node.node_type)

    await db.flush()

    if enqueue_advance and advance_targets and not settings.WORKFLOW_INLINE_NODE_EXECUTION:
        from backend.workers.tasks import advance_workflow_run_task

        for queued_tenant_id, queued_run_id in advance_targets:
            advance_workflow_run_task.delay(
                tenant_id=queued_tenant_id,
                run_id=queued_run_id,
            )

    return results
