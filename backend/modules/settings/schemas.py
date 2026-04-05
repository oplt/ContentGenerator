from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from backend.modules.shared.schemas import ORMModel


class TenantSettingsRequest(BaseModel):
    name: str | None = None
    timezone: str | None = None
    settings: dict[str, str] = Field(default_factory=dict)


class TenantSettingsResponse(ORMModel):
    id: UUID
    name: str
    slug: str
    plan_tier: str
    timezone: str
    status: str
    settings: dict[str, str]


class TelegramSettingsRequest(BaseModel):
    bot_token: str | None = None
    chat_id: str | None = None
    enabled: bool | None = None


class TelegramSettingsResponse(BaseModel):
    bot_token_configured: bool
    chat_id: str
    enabled: bool


class WhatsAppSettingsRequest(BaseModel):
    recipient: str | None = None
    provider: str | None = None
    phone_number_id: str | None = None
    business_account_id: str | None = None
    verify_token: str | None = None
    access_token: str | None = None
    app_secret: str | None = None


class WhatsAppSettingsResponse(BaseModel):
    recipient: str
    provider: str
    phone_number_id: str
    business_account_id: str
    verify_token: str
    access_token_configured: bool
    app_secret_configured: bool
    using_tenant_recipient: bool
    using_tenant_credentials: bool
