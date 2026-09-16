"""FetchMetrics — wrap AnalyticsService (Phase 12)."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field

from backend.modules.workflows.nodes.base import (
    NodeImplementationStatus,
    NodePort,
    NodeResult,
    NodeResultStatus,
    WorkflowNode,
    WorkflowNodeContext,
)


class FetchMetricsConfig(BaseModel):
    sync: bool = True


class FetchMetricsInput(BaseModel):
    social_account_id: UUID | None = None


class FetchMetricsOutput(BaseModel):
    synced: bool
    snapshot_count: int = 0
    post_count: int = 0
    summary: list[dict[str, object]] = Field(default_factory=list)


class FetchMetricsNode(WorkflowNode[FetchMetricsConfig, FetchMetricsInput, FetchMetricsOutput]):
    """Sync/fetch engagement metrics via AnalyticsService."""

    type = "fetch_metrics"
    version = 1
    category = "analytics"
    display_name = "Fetch Metrics"
    description = "Sync published-post analytics snapshots (and return overview counts)."
    implementation_status = NodeImplementationStatus.STABLE
    ConfigSchema = FetchMetricsConfig
    InputSchema = FetchMetricsInput
    OutputSchema = FetchMetricsOutput
    required_capabilities = []
    input_ports = [
        NodePort(name="social_account_id", data_type="uuid", required=False),
    ]
    output_ports = [
        NodePort(name="synced", data_type="boolean"),
        NodePort(name="snapshot_count", data_type="number"),
        NodePort(name="post_count", data_type="number"),
        NodePort(name="summary", data_type="array", required=False),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        if context.db is None:
            return NodeResult(
                status=NodeResultStatus.FAILED,
                error={"code": "missing_db", "message": "FetchMetrics requires a DB session"},
            )
        typed_in = FetchMetricsInput.model_validate(inputs.model_dump())
        typed_cfg = FetchMetricsConfig.model_validate(config.model_dump())

        from backend.modules.analytics.service import AnalyticsService

        svc = AnalyticsService(context.db)
        try:
            synced = False
            synced_count = 0
            if typed_cfg.sync:
                synced_rows = await svc.sync_snapshots(context.tenant_id)
                synced_count = len(synced_rows)
                synced = True
            overview = await svc.overview(
                context.tenant_id,
                social_account_id=typed_in.social_account_id,
            )
        except HTTPException as exc:
            detail = exc.detail
            message = detail if isinstance(detail, str) else str(detail)
            return NodeResult(
                status=NodeResultStatus.FAILED,
                error={
                    "code": "fetch_metrics_failed",
                    "message": message,
                    "status_code": exc.status_code,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return NodeResult(
                status=NodeResultStatus.FAILED,
                error={
                    "code": "fetch_metrics_error",
                    "message": str(exc) or exc.__class__.__name__,
                },
            )

        summary_rows: list[dict[str, object]] = [dict(row) for row in (overview.summary or [])]
        posts = 0
        for row in summary_rows:
            if str(row.get("key") or "") == "posts":
                try:
                    posts = int(str(row.get("value") or 0))
                except (TypeError, ValueError):
                    posts = 0
                break

        if not typed_cfg.sync:
            # Fall back to tracked count from funnel when not syncing.
            for point in overview.publishing_funnel or []:
                if getattr(point, "label", "") == "Tracked":
                    synced_count = int(getattr(point, "value", 0) or 0)
                    break

        output = FetchMetricsOutput(
            synced=synced,
            snapshot_count=synced_count,
            post_count=posts,
            summary=summary_rows,
        )
        return NodeResult(
            status=NodeResultStatus.SUCCEEDED,
            output=output.model_dump(mode="json"),
        )
