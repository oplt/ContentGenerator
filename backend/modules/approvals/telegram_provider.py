from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from backend.core.http import request
from backend.modules.approvals.callback_signing import build_signed_callback_data
from backend.modules.approvals.telegram_asset_cards import TelegramAssetCardMixin
from backend.modules.approvals.telegram_topic_cards import TelegramTopicCardMixin


class TelegramProvider(TelegramTopicCardMixin, TelegramAssetCardMixin):
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
                "inline_keyboard": [
                    [
                        {
                            "text": "✅ Confirm",
                            "callback_data": build_signed_callback_data("approve", approval_request_id),
                        },
                        {
                            "text": "❌ Reject",
                            "callback_data": build_signed_callback_data("reject", approval_request_id),
                        },
                        {
                            "text": "✏️ Update",
                            "callback_data": build_signed_callback_data("revise", approval_request_id),
                        },
                    ]
                ]
            }
        response = await request(
            "POST",
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            provider="approvals",
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
        await request(
            "POST",
            f"https://api.telegram.org/bot{self.bot_token}/editMessageText",
            provider="approvals",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": new_text,
                "parse_mode": parse_mode,
                "reply_markup": {"inline_keyboard": []},
            },
        )

    async def answer_callback(self, callback_query_id: str, text: str) -> None:
        await request(
            "POST",
            f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery",
            provider="approvals",
            json={"callback_query_id": callback_query_id, "text": text},
        )

    async def set_webhook(self, url: str, secret_token: str = "") -> dict[str, Any]:
        body: dict[str, Any] = {
            "url": url,
            "allowed_updates": ["callback_query", "message"],
        }
        if secret_token:
            body["secret_token"] = secret_token
        response = await request(
            "POST",
            f"https://api.telegram.org/bot{self.bot_token}/setWebhook",
            provider="approvals",
            json=body,
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())


class MockTelegramProvider(TelegramProvider):
    async def send_message(
        self,
        text: str,
        approval_request_id: str | None = None,
        *,
        parse_mode: str = "HTML",
    ) -> dict[str, str]:
        _ = parse_mode
        digest = hashlib.sha256(f"{text}:{approval_request_id or ''}".encode()).hexdigest()[:12]
        return {"provider": "telegram-mock", "message_id": digest}

    async def send_topic_card(self, **kwargs: Any) -> dict[str, str]:
        digest = hashlib.sha256(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()[:12]
        return {"provider": "telegram-mock", "message_id": digest}

    async def send_brief_card(self, **kwargs: Any) -> dict[str, str]:
        digest = hashlib.sha256(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()[:12]
        return {"provider": "telegram-mock", "message_id": digest, "short_id": kwargs["short_id"]}

    async def send_twitter_post_card(self, **kwargs: Any) -> dict[str, str]:
        digest = hashlib.sha256(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()[:12]
        return {"provider": "telegram-mock", "message_id": digest}

    async def send_asset_card(self, **kwargs: Any) -> dict[str, str]:
        digest = hashlib.sha256(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()[:12]
        return {"provider": "telegram-mock", "message_id": digest}

    async def send_publish_card(self, **kwargs: Any) -> dict[str, str]:
        digest = hashlib.sha256(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()[:12]
        return {"provider": "telegram-mock", "message_id": digest}

    async def edit_message(
        self, *, chat_id: str, message_id: str, new_text: str, parse_mode: str = "HTML"
    ) -> None:
        return None

    async def answer_callback(self, callback_query_id: str, text: str) -> None:
        return None

    async def set_webhook(self, url: str, secret_token: str = "") -> dict[str, Any]:
        return {
            "ok": True,
            "provider": "telegram-mock",
            "url": url,
            "secret_token": secret_token,
        }


def get_telegram_provider(bot_token: str, chat_id: str) -> TelegramProvider:
    if not bot_token or bot_token.startswith("mock") or bot_token == "test-bot-token":
        return MockTelegramProvider(bot_token=bot_token, chat_id=chat_id)
    return TelegramProvider(bot_token=bot_token, chat_id=chat_id)
