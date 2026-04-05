from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.security import decrypt_secret, encrypt_secret
from backend.modules.approvals.providers import WhatsAppRuntimeConfig
from backend.modules.settings.repository import SettingsRepository
from backend.modules.settings.schemas import (
    TelegramSettingsRequest,
    TelegramSettingsResponse,
    TenantSettingsRequest,
    WhatsAppSettingsRequest,
    WhatsAppSettingsResponse,
)


TELEGRAM_BOT_TOKEN_KEY = "approval.telegram_bot_token_encrypted"
TELEGRAM_CHAT_ID_KEY = "approval.telegram_chat_id"
TELEGRAM_ENABLED_KEY = "approval.telegram_enabled"

WHATSAPP_RECIPIENT_KEY = "approval.whatsapp_recipient"
WHATSAPP_PROVIDER_KEY = "approval.whatsapp_provider"
WHATSAPP_PHONE_NUMBER_ID_KEY = "approval.whatsapp_phone_number_id"
WHATSAPP_BUSINESS_ACCOUNT_ID_KEY = "approval.whatsapp_business_account_id"
WHATSAPP_VERIFY_TOKEN_KEY = "approval.whatsapp_verify_token"
WHATSAPP_ACCESS_TOKEN_KEY = "approval.whatsapp_access_token_encrypted"
WHATSAPP_APP_SECRET_KEY = "approval.whatsapp_app_secret_encrypted"


class SettingsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = SettingsRepository(db)

    async def get_tenant_settings(self, tenant_id: UUID):
        tenant = await self.repo.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return tenant

    async def update_tenant_settings(self, tenant_id: UUID, payload: TenantSettingsRequest):
        tenant = await self.get_tenant_settings(tenant_id)
        if payload.name is not None:
            tenant.name = payload.name
        if payload.timezone is not None:
            tenant.timezone = payload.timezone
        tenant.settings = tenant.settings | payload.settings
        await self.db.flush()
        return tenant

    @staticmethod
    def _global_whatsapp_runtime_config() -> WhatsAppRuntimeConfig:
        return WhatsAppRuntimeConfig(
            recipient=settings.WHATSAPP_DEFAULT_RECIPIENT,
            provider=settings.WHATSAPP_PROVIDER,
            phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID,
            business_account_id=settings.WHATSAPP_BUSINESS_ACCOUNT_ID,
            verify_token=settings.WHATSAPP_VERIFY_TOKEN,
            access_token=settings.WHATSAPP_ACCESS_TOKEN,
            app_secret=settings.WHATSAPP_APP_SECRET,
        )

    @staticmethod
    def _normalize_setting_value(value: str | None) -> str:
        return value.strip() if value else ""

    async def get_whatsapp_settings(self, tenant_id: UUID) -> WhatsAppSettingsResponse:
        tenant = await self.get_tenant_settings(tenant_id)
        current_settings = tenant.settings or {}
        runtime = await self.resolve_whatsapp_runtime_config(tenant_id)
        return WhatsAppSettingsResponse(
            recipient=runtime.recipient,
            provider=runtime.provider,
            phone_number_id=runtime.phone_number_id,
            business_account_id=runtime.business_account_id,
            verify_token=runtime.verify_token,
            access_token_configured=bool(runtime.access_token),
            app_secret_configured=bool(runtime.app_secret),
            using_tenant_recipient=WHATSAPP_RECIPIENT_KEY in current_settings,
            using_tenant_credentials=any(
                key in current_settings
                for key in (
                    WHATSAPP_PROVIDER_KEY,
                    WHATSAPP_PHONE_NUMBER_ID_KEY,
                    WHATSAPP_BUSINESS_ACCOUNT_ID_KEY,
                    WHATSAPP_VERIFY_TOKEN_KEY,
                    WHATSAPP_ACCESS_TOKEN_KEY,
                    WHATSAPP_APP_SECRET_KEY,
                )
            ),
        )

    async def update_whatsapp_settings(
        self,
        tenant_id: UUID,
        payload: WhatsAppSettingsRequest,
    ) -> WhatsAppSettingsResponse:
        tenant = await self.get_tenant_settings(tenant_id)
        current_settings = dict(tenant.settings or {})
        fields_set = payload.model_fields_set

        plain_field_map = {
            "recipient": WHATSAPP_RECIPIENT_KEY,
            "provider": WHATSAPP_PROVIDER_KEY,
            "phone_number_id": WHATSAPP_PHONE_NUMBER_ID_KEY,
            "business_account_id": WHATSAPP_BUSINESS_ACCOUNT_ID_KEY,
            "verify_token": WHATSAPP_VERIFY_TOKEN_KEY,
        }
        secret_field_map = {
            "access_token": WHATSAPP_ACCESS_TOKEN_KEY,
            "app_secret": WHATSAPP_APP_SECRET_KEY,
        }

        for field_name, setting_key in plain_field_map.items():
            if field_name not in fields_set:
                continue
            normalized = self._normalize_setting_value(getattr(payload, field_name))
            if normalized:
                current_settings[setting_key] = normalized
            else:
                current_settings.pop(setting_key, None)

        for field_name, setting_key in secret_field_map.items():
            if field_name not in fields_set:
                continue
            normalized = self._normalize_setting_value(getattr(payload, field_name))
            if normalized:
                current_settings[setting_key] = encrypt_secret(normalized)
            else:
                current_settings.pop(setting_key, None)

        tenant.settings = current_settings
        await self.db.flush()
        return await self.get_whatsapp_settings(tenant_id)

    async def resolve_whatsapp_runtime_config(self, tenant_id: UUID) -> WhatsAppRuntimeConfig:
        tenant = await self.get_tenant_settings(tenant_id)
        current_settings = tenant.settings or {}
        base = self._global_whatsapp_runtime_config()

        recipient = current_settings.get(WHATSAPP_RECIPIENT_KEY) or base.recipient
        provider = current_settings.get(WHATSAPP_PROVIDER_KEY) or base.provider
        phone_number_id = current_settings.get(WHATSAPP_PHONE_NUMBER_ID_KEY) or base.phone_number_id
        business_account_id = (
            current_settings.get(WHATSAPP_BUSINESS_ACCOUNT_ID_KEY) or base.business_account_id
        )
        verify_token = current_settings.get(WHATSAPP_VERIFY_TOKEN_KEY) or base.verify_token

        encrypted_access_token = current_settings.get(WHATSAPP_ACCESS_TOKEN_KEY)
        encrypted_app_secret = current_settings.get(WHATSAPP_APP_SECRET_KEY)
        access_token = (
            decrypt_secret(encrypted_access_token)
            if encrypted_access_token
            else base.access_token
        )
        app_secret = (
            decrypt_secret(encrypted_app_secret)
            if encrypted_app_secret
            else base.app_secret
        )

        return WhatsAppRuntimeConfig(
            recipient=recipient,
            provider=provider,
            phone_number_id=phone_number_id,
            business_account_id=business_account_id,
            verify_token=verify_token,
            access_token=access_token,
            app_secret=app_secret,
        )

    async def find_tenant_id_by_whatsapp_phone_number_id(self, phone_number_id: str) -> UUID | None:
        normalized = self._normalize_setting_value(phone_number_id)
        if not normalized:
            return None
        for tenant in await self.repo.list_tenants():
            settings_map = tenant.settings or {}
            if settings_map.get(WHATSAPP_PHONE_NUMBER_ID_KEY) == normalized:
                return tenant.id
        return None

    async def get_telegram_settings(self, tenant_id: UUID) -> TelegramSettingsResponse:
        tenant = await self.get_tenant_settings(tenant_id)
        s = tenant.settings or {}
        return TelegramSettingsResponse(
            bot_token_configured=bool(s.get(TELEGRAM_BOT_TOKEN_KEY)),
            chat_id=s.get(TELEGRAM_CHAT_ID_KEY, ""),
            enabled=s.get(TELEGRAM_ENABLED_KEY, "false").lower() == "true",
        )

    async def update_telegram_settings(
        self, tenant_id: UUID, payload: TelegramSettingsRequest
    ) -> TelegramSettingsResponse:
        tenant = await self.get_tenant_settings(tenant_id)
        current_settings = dict(tenant.settings or {})
        fields_set = payload.model_fields_set

        if "bot_token" in fields_set:
            normalized = self._normalize_setting_value(payload.bot_token)
            if normalized:
                current_settings[TELEGRAM_BOT_TOKEN_KEY] = encrypt_secret(normalized)
            else:
                current_settings.pop(TELEGRAM_BOT_TOKEN_KEY, None)

        if "chat_id" in fields_set:
            normalized = self._normalize_setting_value(payload.chat_id)
            if normalized:
                current_settings[TELEGRAM_CHAT_ID_KEY] = normalized
            else:
                current_settings.pop(TELEGRAM_CHAT_ID_KEY, None)

        if "enabled" in fields_set and payload.enabled is not None:
            current_settings[TELEGRAM_ENABLED_KEY] = str(payload.enabled).lower()

        tenant.settings = current_settings
        await self.db.flush()
        return await self.get_telegram_settings(tenant_id)

    async def resolve_telegram_runtime_config(self, tenant_id: UUID) -> dict[str, str | bool]:
        tenant = await self.get_tenant_settings(tenant_id)
        s = tenant.settings or {}
        encrypted_token = s.get(TELEGRAM_BOT_TOKEN_KEY)
        return {
            "bot_token": decrypt_secret(encrypted_token) if encrypted_token else "",
            "chat_id": s.get(TELEGRAM_CHAT_ID_KEY, ""),
            "enabled": s.get(TELEGRAM_ENABLED_KEY, "false").lower() == "true",
        }

    async def verify_whatsapp_verify_token(self, verify_token: str) -> bool:
        if verify_token == settings.WHATSAPP_VERIFY_TOKEN:
            return True
        normalized = self._normalize_setting_value(verify_token)
        if not normalized:
            return False
        for tenant in await self.repo.list_tenants():
            if (tenant.settings or {}).get(WHATSAPP_VERIFY_TOKEN_KEY) == normalized:
                return True
        return False
