from __future__ import annotations

import uuid

from backend.core.config import settings
from backend.modules.approvals.service import ApprovalService
from backend.modules.settings.schemas import WhatsAppSettingsRequest
from backend.modules.settings.service import (
    WHATSAPP_ACCESS_TOKEN_KEY,
    SettingsService,
)


async def test_whatsapp_settings_are_encrypted_and_resolved(db_session, seeded_context, monkeypatch):
    tenant = seeded_context["tenant"]
    service = SettingsService(db_session)

    monkeypatch.setattr(settings, "WHATSAPP_DEFAULT_RECIPIENT", "+10000000000")
    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER", "stub")
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    monkeypatch.setattr(settings, "WHATSAPP_BUSINESS_ACCOUNT_ID", "")
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "global-verify")
    monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "")

    result = await service.update_whatsapp_settings(
        tenant.id,
        WhatsAppSettingsRequest(
            recipient="+15551234567",
            provider="meta",
            phone_number_id="123456789",
            business_account_id="987654321",
            verify_token="tenant-verify",
            access_token="tenant-access-token",
            app_secret="tenant-app-secret",
        ),
    )
    await db_session.commit()

    tenant_model = await service.get_tenant_settings(tenant.id)
    assert tenant_model.settings[WHATSAPP_ACCESS_TOKEN_KEY] != "tenant-access-token"

    runtime = await service.resolve_whatsapp_runtime_config(tenant.id)
    assert runtime.recipient == "+15551234567"
    assert runtime.provider == "meta"
    assert runtime.phone_number_id == "123456789"
    assert runtime.access_token == "tenant-access-token"
    assert runtime.app_secret == "tenant-app-secret"
    assert result.using_tenant_recipient is True
    assert result.using_tenant_credentials is True


async def test_whatsapp_verify_token_accepts_tenant_override(db_session, seeded_context, monkeypatch):
    tenant = seeded_context["tenant"]
    service = SettingsService(db_session)

    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "global-verify")

    await service.update_whatsapp_settings(
        tenant.id,
        WhatsAppSettingsRequest(verify_token="tenant-verify"),
    )

    assert await service.verify_whatsapp_verify_token("tenant-verify") is True
    assert await service.verify_whatsapp_verify_token("global-verify") is True
    assert await service.verify_whatsapp_verify_token("wrong-token") is False


async def test_send_for_approval_uses_tenant_whatsapp_recipient(
    db_session,
    seeded_context,
    monkeypatch,
):
    tenant = seeded_context["tenant"]
    settings_service = SettingsService(db_session)

    monkeypatch.setattr(settings, "WHATSAPP_DEFAULT_RECIPIENT", "+19990000000")

    await settings_service.update_whatsapp_settings(
        tenant.id,
        WhatsAppSettingsRequest(recipient="+15557654321"),
    )

    async def fake_build_summary_text(self, tenant_id, content_job_id, approval_request_id):
        return f"Approval request {approval_request_id}"

    monkeypatch.setattr(ApprovalService, "_build_summary_text", fake_build_summary_text)

    service = ApprovalService(db_session)
    request = await service.send_for_approval(
        tenant_id=tenant.id,
        content_job_id=uuid.uuid4(),
        recipient=None,
    )

    assert request.recipient == "+15557654321"
    assert request.provider == "stub"
