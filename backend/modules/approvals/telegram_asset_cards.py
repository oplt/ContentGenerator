from __future__ import annotations

from typing import Any

from backend.core.http import request
from backend.modules.approvals.callback_signing import build_signed_callback_data

_RISK_EMOJI = {
    "safe": "🟢",
    "sensitive": "🟡",
    "risky": "🟠",
    "unsafe": "🔴",
    "low": "🟢",
    "medium": "🟡",
    "high": "🟠",
    "blocked": "🔴",
}


class TelegramAssetCardMixin:
    """Asset / publish / twitter approval cards (Gate 2+)."""

    bot_token: str
    chat_id: str

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
        _ = selected_platforms
        displayed_label = risk_label or risk_level
        risk_emoji = _RISK_EMOJI.get(displayed_label, "⚪")
        previews_text = (
            "\n\n".join(f"<i>{p}</i>" for p in platform_previews[:3]) or "<i>No preview available</i>"
        )
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
                        {
                            "text": "✅ Approve Assets",
                            "callback_data": build_signed_callback_data("approve", approval_request_id),
                        },
                        {
                            "text": "❌ Reject",
                            "callback_data": build_signed_callback_data("reject", approval_request_id),
                        },
                        {
                            "text": "✏️ Revise",
                            "callback_data": build_signed_callback_data("revise", approval_request_id),
                        },
                    ],
                    [
                        {
                            "text": "✂️ Trim",
                            "callback_data": build_signed_callback_data("trim", approval_request_id),
                        },
                        {
                            "text": "🎯 Edit CTA",
                            "callback_data": build_signed_callback_data("edit_cta", approval_request_id),
                        },
                    ],
                    [
                        {
                            "text": "📣 Publish Gate",
                            "callback_data": build_signed_callback_data("publish_gate", approval_request_id),
                        },
                    ],
                ]
            },
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
        inline_rows: list[list[dict[str, str]]] = [
            [
                {
                    "text": "✅ Approve All",
                    "callback_data": build_signed_callback_data("approve_publish", approval_request_id),
                },
                {
                    "text": "⏸ Hold",
                    "callback_data": build_signed_callback_data("hold_publish", approval_request_id),
                },
                {
                    "text": "🛑 Cancel",
                    "callback_data": build_signed_callback_data("cancel_publish", approval_request_id),
                },
            ]
        ]
        for platform in platforms[:4]:
            inline_rows.append(
                [
                    {
                        "text": f"Only {platform.upper()}",
                        "callback_data": build_signed_callback_data(
                            f"approve_{platform}", approval_request_id
                        ),
                    }
                ]
            )
        inline_rows.append(
            [
                {
                    "text": "🕒 Schedule Later",
                    "callback_data": build_signed_callback_data("schedule_publish", approval_request_id),
                },
            ]
        )
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": inline_rows},
        }
        response = await request(
            "POST",
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            provider="approvals",
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
            f'<b>🐦 Twitter Post — <a href="{repo_url}">{repo_name}</a></b>\n\n'
            f"{post_text}"
        )
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "✅ Post", "callback_data": build_signed_callback_data("tw_post", post_id)},
                        {"text": "✏️ Edit", "callback_data": build_signed_callback_data("tw_edit", post_id)},
                        {"text": "❌ Reject", "callback_data": build_signed_callback_data("tw_reject", post_id)},
                    ]
                ]
            },
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
