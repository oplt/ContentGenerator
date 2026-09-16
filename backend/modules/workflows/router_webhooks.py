"""Public workflow webhook ingress (Phase 17) — no session auth; HMAC required."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.db import get_db
from backend.core.config import settings
from backend.core.rate_limit import rate_limit_request
from backend.modules.workflows.webhook_ingress import receive_workflow_webhook

router = APIRouter()


class WorkflowWebhookAccepted(BaseModel):
    inbox_id: str
    workflow_run_id: str | None = None
    deduped: bool = False
    status: str


@router.post("/webhooks/{endpoint_id}", response_model=WorkflowWebhookAccepted, status_code=202)
async def ingest_workflow_webhook(
    endpoint_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> WorkflowWebhookAccepted:
    await rate_limit_request(
        request,
        bucket="workflow_webhook",
        max_attempts=settings.RATE_LIMIT_DEFAULT_MAX_ATTEMPTS,
        window_seconds=settings.RATE_LIMIT_DEFAULT_WINDOW_SECONDS,
    )
    await rate_limit_request(
        request,
        bucket=f"workflow_webhook:{endpoint_id}",
        max_attempts=120,
        window_seconds=60,
    )

    raw_body = await request.body()
    if len(raw_body) > 256_000:
        raise HTTPException(status_code=413, detail="Webhook body too large")

    headers = {k: v for k, v in request.headers.items()}
    result = await receive_workflow_webhook(
        db,
        endpoint_id=endpoint_id,
        raw_body=raw_body,
        headers=headers,
        process_inline=bool(settings.WORKFLOW_INLINE_NODE_EXECUTION),
    )
    return WorkflowWebhookAccepted.model_validate(result)
