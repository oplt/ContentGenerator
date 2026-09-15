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


class TelegramTopicCardMixin:
    """Topic / editorial-brief approval cards (Gate 1)."""

    bot_token: str
    chat_id: str

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
                        {
                            "text": "✅ Approve Topic",
                            "callback_data": build_signed_callback_data("approve_topic", callback_id),
                        },
                        {
                            "text": "❌ Reject",
                            "callback_data": build_signed_callback_data("reject_topic", callback_id),
                        },
                    ],
                    [
                        {
                            "text": "🛡 Safer Angle",
                            "callback_data": build_signed_callback_data("safer_topic", callback_id),
                        },
                        {
                            "text": "⏸ Hold",
                            "callback_data": build_signed_callback_data("hold_topic", callback_id),
                        },
                    ],
                    [
                        {
                            "text": "♻️ Regen Brief",
                            "callback_data": build_signed_callback_data("regen_topic", callback_id),
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
        risk_emoji = _RISK_EMOJI.get(risk_label or risk_level, "⚪")
        text = (
            f"<b>📋 Editorial Brief — Topic Approval</b>\n\n"
            f"<b>Headline:</b> {headline}\n"
            f"<b>Angle:</b> {angle}\n\n"
            f"<b>Why now:</b> {why_now or 'Emerging multi-source trend'}\n"
            f"<b>CTA:</b> {cta_strategy or 'Follow for updates'}\n"
            f"<b>Platforms:</b> {', '.join(platform_targets or [])}\n\n"
            f"<b>Talking Points:</b>\n{points_text}\n\n"
            f"<b>Tone:</b> {tone}  |  <b>Vertical:</b> {content_vertical}  |  "
            f"<b>Risk:</b> {risk_emoji} {risk_level}\n"
            f"<b>Review label:</b> {risk_label or risk_level}"
        )
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {
                            "text": "✅ Approve Brief",
                            "callback_data": build_signed_callback_data("approve_brief", short_id),
                        },
                        {
                            "text": "❌ Reject Brief",
                            "callback_data": build_signed_callback_data("reject_brief", short_id),
                        },
                    ],
                    [
                        {
                            "text": "🛡 Safer Angle",
                            "callback_data": build_signed_callback_data("safer_brief", short_id),
                        },
                        {
                            "text": "🪶 Soften Tone",
                            "callback_data": build_signed_callback_data("soften_brief", short_id),
                        },
                    ],
                    [
                        {
                            "text": "📝 Text Only",
                            "callback_data": build_signed_callback_data("text_only_brief", short_id),
                        },
                        {
                            "text": "🎬 Text + Video",
                            "callback_data": build_signed_callback_data("text_video_brief", short_id),
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
        return {"provider": "telegram", "message_id": message_id, "short_id": short_id}
