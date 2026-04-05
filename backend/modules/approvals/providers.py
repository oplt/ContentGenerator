from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx

from backend.core.config import settings

@dataclass
class ParsedWhatsAppMessage:
    approval_request_id: UUID | None
    raw_text: str
    intent: str
    confidence: float
    feedback: str | None
    provider_message_id: str | None


@dataclass
class WhatsAppRuntimeConfig:
    provider: str
    recipient: str
    access_token: str
    phone_number_id: str
    business_account_id: str
    verify_token: str
    app_secret: str


class WhatsAppProvider:
    async def send_message(self, *, to: str, text: str) -> dict[str, str]:
        raise NotImplementedError

    def verify_signature(self, *, body: bytes, signature: str | None) -> bool:
        return True

    def parse_payload(self, payload: dict[str, Any]) -> list[ParsedWhatsAppMessage]:
        raise NotImplementedError


class StubWhatsAppProvider(WhatsAppProvider):
    async def send_message(self, *, to: str, text: str) -> dict[str, str]:
        return {"provider": "stub", "message_id": hashlib.sha256(text.encode()).hexdigest()[:16]}

    def parse_payload(self, payload: dict[str, Any]) -> list[ParsedWhatsAppMessage]:
        raw_text = str(payload.get("text", ""))
        request_id = payload.get("approval_request_id")
        lowered = raw_text.lower().strip()
        intent = "unknown"
        confidence = 0.4
        feedback = None
        if lowered.startswith("approve"):
            intent = "approve"
            confidence = 0.98
        elif lowered.startswith("reject"):
            intent = "reject"
            confidence = 0.95
        elif lowered.startswith("revise"):
            intent = "revise"
            confidence = 0.95
            feedback = raw_text.partition(" ")[2].strip() or "Please revise"
            feedback_parts = feedback.split(" ", maxsplit=1)
            if len(feedback_parts) == 2:
                feedback = feedback_parts[1]
        return [
            ParsedWhatsAppMessage(
                approval_request_id=UUID(request_id) if request_id else None,
                raw_text=raw_text,
                intent=intent,
                confidence=confidence,
                feedback=feedback,
                provider_message_id=payload.get("message_id"),
            )
        ]


class MetaWhatsAppCloudProvider(WhatsAppProvider):
    def __init__(self, config: WhatsAppRuntimeConfig):
        self.config = config

    async def send_message(self, *, to: str, text: str) -> dict[str, str]:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"https://graph.facebook.com/v20.0/{self.config.phone_number_id}/messages",
                headers={"Authorization": f"Bearer {self.config.access_token}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "text",
                    "text": {"body": text},
                },
            )
            response.raise_for_status()
            payload = response.json()
            message_id = payload.get("messages", [{}])[0].get("id")
            return {"provider": "meta", "message_id": str(message_id)}

    def verify_signature(self, *, body: bytes, signature: str | None) -> bool:
        if not signature or not self.config.app_secret:
            return False
        digest = hmac.new(
            self.config.app_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        expected = f"sha256={digest}"
        return hmac.compare_digest(expected, signature)

    def parse_payload(self, payload: dict[str, Any]) -> list[ParsedWhatsAppMessage]:
        parsed: list[ParsedWhatsAppMessage] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    text = message.get("text", {}).get("body", "")
                    lowered = text.lower()
                    intent = "approve" if lowered.startswith("approve") else "revise" if lowered.startswith("revise") else "reject" if lowered.startswith("reject") else "unknown"
                    feedback = text.partition(" ")[2].strip() if intent == "revise" else None
                    parsed.append(
                        ParsedWhatsAppMessage(
                            approval_request_id=None,
                            raw_text=text,
                            intent=intent,
                            confidence=0.9 if intent != "unknown" else 0.35,
                            feedback=feedback,
                            provider_message_id=message.get("id"),
                        )
                    )
        return parsed


def get_whatsapp_provider(config: WhatsAppRuntimeConfig) -> WhatsAppProvider:
    if config.provider == "meta" and config.access_token and config.phone_number_id:
        return MetaWhatsAppCloudProvider(config)
    return StubWhatsAppProvider()


class TelegramProvider:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send_message(self, text: str, approval_request_id: str | None = None) -> dict[str, str]:
        payload: dict[str, Any] = {"chat_id": self.chat_id, "text": text}
        if approval_request_id:
            payload["reply_markup"] = {
                "inline_keyboard": [[
                    {"text": "✅ Confirm", "callback_data": f"approve:{approval_request_id}"},
                    {"text": "❌ Reject",  "callback_data": f"reject:{approval_request_id}"},
                    {"text": "✏️ Update",  "callback_data": f"revise:{approval_request_id}"},
                ]]
            }
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            message_id = str(data.get("result", {}).get("message_id", ""))
            return {"provider": "telegram", "message_id": message_id}

    async def answer_callback(self, callback_query_id: str, text: str) -> None:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery",
                json={"callback_query_id": callback_query_id, "text": text},
            )

    async def set_webhook(self, url: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/setWebhook",
                json={"url": url, "allowed_updates": ["callback_query", "message"]},
            )
            response.raise_for_status()
            return response.json()
