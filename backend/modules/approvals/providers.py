from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx

from backend.core.config import settings


def sign_telegram_callback(payload: str) -> str:
    digest = hmac.new(
        settings.telegram_callback_signing_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:10]


def build_signed_callback_data(action: str, identifier: str) -> str:
    payload = f"{action}:{identifier}"
    return f"{payload}:{sign_telegram_callback(payload)}"


def verify_signed_callback_data(data: str) -> tuple[bool, str, str]:
    parts = data.split(":")
    if len(parts) < 2:
        return False, "", ""
    if len(parts) == 2:
        return True, parts[0], parts[1]
    action, identifier, signature = parts[0], parts[1], parts[2]
    payload = f"{action}:{identifier}"
    return hmac.compare_digest(signature, sign_telegram_callback(payload)), action, identifier


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

    async def send_message(
        self,
        text: str,
        approval_request_id: str | None = None,
        *,
        parse_mode: str = "HTML",
    ) -> dict[str, str]:
        payload: dict[str, Any] = {"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode}
        if approval_request_id:
            payload["reply_markup"] = {
                "inline_keyboard": [[
                    {"text": "✅ Confirm", "callback_data": build_signed_callback_data("approve", approval_request_id)},
                    {"text": "❌ Reject",  "callback_data": build_signed_callback_data("reject", approval_request_id)},
                    {"text": "✏️ Update",  "callback_data": build_signed_callback_data("revise", approval_request_id)},
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

    async def send_topic_card(
        self,
        *,
        title: str,
        score: float,
        why_now: str,
        evidence_links: list[str],
        risk_level: str,
        risk_label: str | None = None,
        callback_id: str,
    ) -> dict[str, str]:
        evidence_text = "\n".join(f"• {link}" for link in evidence_links[:3]) or "• No evidence links"
        text = (
            f"<b>📡 Topic Approval</b>\n\n"
            f"<b>{title}</b>\n"
            f"<b>Score:</b> {score:.2f}\n"
            f"<b>Why now:</b> {why_now}\n"
            f"<b>Risk:</b> {risk_level}\n"
            f"<b>Review label:</b> {risk_label or risk_level}\n\n"
            f"<b>Evidence:</b>\n{evidence_text}"
        )
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "✅ Approve Topic", "callback_data": build_signed_callback_data("approve_topic", callback_id)},
                        {"text": "❌ Reject", "callback_data": build_signed_callback_data("reject_topic", callback_id)},
                    ],
                    [
                        {"text": "🛡 Safer Angle", "callback_data": build_signed_callback_data("safer_topic", callback_id)},
                        {"text": "⏸ Hold", "callback_data": build_signed_callback_data("hold_topic", callback_id)},
                    ],
                    [
                        {"text": "♻️ Regen Brief", "callback_data": build_signed_callback_data("regen_topic", callback_id)},
                    ],
                ]
            },
        }
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return {"provider": "telegram", "message_id": str(data.get("result", {}).get("message_id", ""))}

    async def send_brief_card(
        self,
        *,
        headline: str,
        angle: str,
        talking_points: list[str],
        tone: str,
        risk_level: str,
        risk_label: str | None = None,
        content_vertical: str,
        why_now: str = "",
        cta_strategy: str = "",
        platform_targets: list[str] | None = None,
        short_id: str,
    ) -> dict[str, str]:
        """
        Gate 1 — send an editorial brief card for topic approval.
        Uses short_id (≤8 chars) in callback_data to stay under Telegram's 64-byte limit.
        """
        points_text = "\n".join(f"  • {pt}" for pt in talking_points[:5])
        risk_emoji = {"safe": "🟢", "sensitive": "🟡", "risky": "🟠", "unsafe": "🔴", "low": "🟢", "medium": "🟡", "high": "🟠", "blocked": "🔴"}.get(risk_label or risk_level, "⚪")
        text = (
            f"<b>📋 Editorial Brief — Topic Approval</b>\n\n"
            f"<b>Headline:</b> {headline}\n"
            f"<b>Angle:</b> {angle}\n\n"
            f"<b>Why now:</b> {why_now or 'Emerging multi-source trend'}\n"
            f"<b>CTA:</b> {cta_strategy or 'Follow for updates'}\n"
            f"<b>Platforms:</b> {', '.join(platform_targets or [])}\n\n"
            f"<b>Talking Points:</b>\n{points_text}\n\n"
            f"<b>Tone:</b> {tone}  |  <b>Vertical:</b> {content_vertical}  |  <b>Risk:</b> {risk_emoji} {risk_level}\n"
            f"<b>Review label:</b> {risk_label or risk_level}"
        )
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "✅ Approve Brief", "callback_data": build_signed_callback_data("approve_brief", short_id)},
                        {"text": "❌ Reject Brief",  "callback_data": build_signed_callback_data("reject_brief", short_id)},
                    ],
                    [
                        {"text": "🛡 Safer Angle", "callback_data": build_signed_callback_data("safer_brief", short_id)},
                        {"text": "🪶 Soften Tone", "callback_data": build_signed_callback_data("soften_brief", short_id)},
                    ],
                    [
                        {"text": "📝 Text Only", "callback_data": build_signed_callback_data("text_only_brief", short_id)},
                        {"text": "🎬 Text + Video", "callback_data": build_signed_callback_data("text_video_brief", short_id)},
                    ],
                ]
            },
        }
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            message_id = str(data.get("result", {}).get("message_id", ""))
            return {"provider": "telegram", "message_id": message_id, "short_id": short_id}

    async def send_asset_card(
        self,
        *,
        headline: str,
        platform_previews: list[str],
        approval_request_id: str,
        risk_level: str = "safe",
        risk_label: str | None = None,
        selected_platforms: list[str] | None = None,
    ) -> dict[str, str]:
        """
        Gate 2 — send a content asset approval card after generation.
        Uses full approval_request_id in callback_data (fits within 64 bytes as UUID).
        """
        displayed_label = risk_label or risk_level
        risk_emoji = {"safe": "🟢", "sensitive": "🟡", "risky": "🟠", "unsafe": "🔴", "low": "🟢", "medium": "🟡", "high": "🟠", "blocked": "🔴"}.get(displayed_label, "⚪")
        previews_text = "\n\n".join(
            f"<i>{p}</i>" for p in platform_previews[:3]
        ) or "<i>No preview available</i>"
        text = (
            f"<b>🎨 Content Ready — Asset Approval</b>  {risk_emoji}\n\n"
            f"<b>{headline}</b>\n\n"
            f"<b>Review label:</b> {displayed_label}\n\n"
            f"{previews_text}"
        )
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "✅ Approve Assets", "callback_data": build_signed_callback_data("approve", approval_request_id)},
                        {"text": "❌ Reject", "callback_data": build_signed_callback_data("reject", approval_request_id)},
                        {"text": "✏️ Revise", "callback_data": build_signed_callback_data("revise", approval_request_id)},
                    ],
                    [
                        {"text": "✂️ Trim", "callback_data": build_signed_callback_data("trim", approval_request_id)},
                        {"text": "🎯 Edit CTA", "callback_data": build_signed_callback_data("edit_cta", approval_request_id)},
                    ],
                    [
                        {"text": "📣 Publish Gate", "callback_data": build_signed_callback_data("publish_gate", approval_request_id)},
                    ],
                ]
            },
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

    async def send_publish_card(
        self,
        *,
        headline: str,
        approval_request_id: str,
        platforms: list[str],
        scheduled_for: str | None = None,
        risk_level: str = "low",
    ) -> dict[str, str]:
        text = (
            f"<b>🚀 Publish Approval</b>\n\n"
            f"<b>{headline}</b>\n"
            f"<b>Platforms:</b> {', '.join(platforms)}\n"
            f"<b>Review label:</b> {risk_level}\n"
            f"<b>Schedule:</b> {scheduled_for or 'Publish now'}"
        )
        inline_rows: list[list[dict[str, str]]] = [[
            {"text": "✅ Approve All", "callback_data": build_signed_callback_data("approve_publish", approval_request_id)},
            {"text": "⏸ Hold", "callback_data": build_signed_callback_data("hold_publish", approval_request_id)},
            {"text": "🛑 Cancel", "callback_data": build_signed_callback_data("cancel_publish", approval_request_id)},
        ]]
        for platform in platforms[:4]:
            inline_rows.append([
                {"text": f"Only {platform.upper()}", "callback_data": build_signed_callback_data(f"approve_{platform}", approval_request_id)}
            ])
        inline_rows.append([
            {"text": "🕒 Schedule Later", "callback_data": build_signed_callback_data("schedule_publish", approval_request_id)},
        ])
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": inline_rows},
        }
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return {"provider": "telegram", "message_id": str(data.get("result", {}).get("message_id", ""))}

    async def send_twitter_post_card(
        self,
        *,
        repo_name: str,
        repo_url: str,
        post_text: str,
        post_id: str,
    ) -> dict[str, str]:
        """Send a Twitter post for approval with Post / Edit / Reject inline buttons."""
        text = (
            f"<b>🐦 Twitter Post — <a href=\"{repo_url}\">{repo_name}</a></b>\n\n"
            f"{post_text}"
        )
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [[
                    {"text": "✅ Post", "callback_data": build_signed_callback_data("tw_post", post_id)},
                    {"text": "✏️ Edit", "callback_data": build_signed_callback_data("tw_edit", post_id)},
                    {"text": "❌ Reject", "callback_data": build_signed_callback_data("tw_reject", post_id)},
                ]]
            },
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

    async def edit_message(
        self,
        *,
        chat_id: str,
        message_id: str,
        new_text: str,
        parse_mode: str = "HTML",
    ) -> None:
        """
        Edit an existing Telegram message in place (removes inline keyboard).
        Used to update approval cards after the operator acts on them.
        """
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/editMessageText",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": new_text,
                    "parse_mode": parse_mode,
                    "reply_markup": {"inline_keyboard": []},
                },
            )

    async def answer_callback(self, callback_query_id: str, text: str) -> None:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery",
                json={"callback_query_id": callback_query_id, "text": text},
            )

    async def set_webhook(self, url: str, secret_token: str = "") -> dict[str, Any]:
        body: dict[str, Any] = {
            "url": url,
            "allowed_updates": ["callback_query", "message"],
        }
        if secret_token:
            body["secret_token"] = secret_token
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/setWebhook",
                json=body,
            )
            response.raise_for_status()
            return response.json()


class MockTelegramProvider(TelegramProvider):
    async def send_message(self, text: str, approval_request_id: str | None = None) -> dict[str, str]:
        digest = hashlib.sha256(f"{text}:{approval_request_id or ''}".encode()).hexdigest()[:12]
        return {"provider": "telegram-mock", "message_id": digest}

    async def send_topic_card(self, **kwargs) -> dict[str, str]:
        digest = hashlib.sha256(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()[:12]
        return {"provider": "telegram-mock", "message_id": digest}

    async def send_brief_card(self, **kwargs) -> dict[str, str]:
        digest = hashlib.sha256(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()[:12]
        return {"provider": "telegram-mock", "message_id": digest, "short_id": kwargs["short_id"]}

    async def send_twitter_post_card(self, **kwargs) -> dict[str, str]:
        digest = hashlib.sha256(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()[:12]
        return {"provider": "telegram-mock", "message_id": digest}

    async def send_asset_card(self, **kwargs) -> dict[str, str]:
        digest = hashlib.sha256(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()[:12]
        return {"provider": "telegram-mock", "message_id": digest}

    async def send_publish_card(self, **kwargs) -> dict[str, str]:
        digest = hashlib.sha256(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()[:12]
        return {"provider": "telegram-mock", "message_id": digest}

    async def edit_message(self, *, chat_id: str, message_id: str, new_text: str, parse_mode: str = "HTML") -> None:
        return None

    async def answer_callback(self, callback_query_id: str, text: str) -> None:
        return None

    async def set_webhook(self, url: str, secret_token: str = "") -> dict[str, Any]:
        return {"ok": True, "provider": "telegram-mock", "url": url, "secret_token": secret_token}


def get_telegram_provider(bot_token: str, chat_id: str) -> TelegramProvider:
    if not bot_token or bot_token.startswith("mock") or bot_token == "test-bot-token":
        return MockTelegramProvider(bot_token=bot_token, chat_id=chat_id)
    return TelegramProvider(bot_token=bot_token, chat_id=chat_id)
