from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.approvals.models import ApprovalMessage, ApprovalRequest, WebhookInbox


class ApprovalRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_request(self, request: ApprovalRequest) -> ApprovalRequest:
        self.db.add(request)
        await self.db.flush()
        return request

    async def create_message(self, message: ApprovalMessage) -> ApprovalMessage:
        self.db.add(message)
        await self.db.flush()
        return message

    async def create_webhook(self, inbox: WebhookInbox) -> WebhookInbox:
        self.db.add(inbox)
        await self.db.flush()
        return inbox

    async def list_requests(self, tenant_id: UUID, limit: int = 50) -> list[ApprovalRequest]:
        result = await self.db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.tenant_id == tenant_id)
            .order_by(ApprovalRequest.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_request(self, tenant_id: UUID, request_id: UUID) -> ApprovalRequest | None:
        result = await self.db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.id == request_id,
                ApprovalRequest.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_request_by_id(self, request_id: UUID) -> ApprovalRequest | None:
        result = await self.db.execute(select(ApprovalRequest).where(ApprovalRequest.id == request_id))
        return result.scalar_one_or_none()

    async def list_messages(self, request_id: UUID) -> list[ApprovalMessage]:
        result = await self.db.execute(
            select(ApprovalMessage)
            .where(ApprovalMessage.approval_request_id == request_id)
            .order_by(ApprovalMessage.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_webhook_by_dedupe_key(self, dedupe_key: str) -> WebhookInbox | None:
        result = await self.db.execute(
            select(WebhookInbox).where(WebhookInbox.dedupe_key == dedupe_key)
        )
        return result.scalar_one_or_none()

    async def get_request_for_content_job(self, content_job_id: UUID) -> ApprovalRequest | None:
        result = await self.db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.content_job_id == content_job_id)
            .order_by(ApprovalRequest.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
