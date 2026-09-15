"""Approvals provider facade — stable import surface for WhatsApp/Telegram providers."""

from __future__ import annotations

from backend.modules.approvals.callback_signing import (
    build_signed_callback_data,
    sign_telegram_callback,
    verify_signed_callback_data,
)
from backend.modules.approvals.telegram_provider import (
    MockTelegramProvider,
    TelegramProvider,
    get_telegram_provider,
)
from backend.modules.approvals.whatsapp_providers import (
    MetaWhatsAppCloudProvider,
    ParsedWhatsAppMessage,
    StubWhatsAppProvider,
    WhatsAppProvider,
    WhatsAppRuntimeConfig,
    get_whatsapp_provider,
)

__all__ = [
    "MetaWhatsAppCloudProvider",
    "MockTelegramProvider",
    "ParsedWhatsAppMessage",
    "StubWhatsAppProvider",
    "TelegramProvider",
    "WhatsAppProvider",
    "WhatsAppRuntimeConfig",
    "build_signed_callback_data",
    "get_telegram_provider",
    "get_whatsapp_provider",
    "sign_telegram_callback",
    "verify_signed_callback_data",
]
