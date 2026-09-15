"""Telegram gate-1 delivery and callback handling for editorial briefs."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException

from backend.core.cache import redis_client
from backend.modules.approvals.providers import TelegramProvider, get_telegram_provider, verify_signed_callback_data
from backend.modules.editorial_briefs.models import BriefStatus, EditorialBrief
from backend.modules.editorial_briefs.schemas import BriefRewriteRequest
from backend.modules.settings.service import SettingsService
from backend.modules.story_intelligence.models import TrendWorkflowState

# Redis key template for brief short-ID → brief UUID mapping
_BRIEF_SHORT_ID_KEY = "brief:short:{short_id}"
_BRIEF_SHORT_ID_TTL = 86400  # 24 hours


class BriefTelegramMixin:
    """Send brief cards to Telegram and process approval callbacks."""

    async def send_to_telegram(self, tenant_id: UUID, brief_id: UUID) -> dict[str, Any]:
        """
        Gate 1 — send editorial brief card to Telegram for topic approval.
        Generates an 8-char short_id, stores brief_id in Redis, sends the card.
        Returns the Telegram API result dict.
        """
        brief = await self._get_or_404(tenant_id, brief_id)
        if brief.status != BriefStatus.READY.value:
            raise HTTPException(
                status_code=409,
                detail=f"Brief must be in 'ready' status to send to Telegram, got '{brief.status}'",
            )

        settings_svc = SettingsService(self.db)
        tg_config = await settings_svc.resolve_telegram_runtime_config(tenant_id)
        if not tg_config.get("enabled") or not tg_config.get("bot_token") or not tg_config.get("chat_id"):
            raise HTTPException(status_code=422, detail="Telegram is not configured or not enabled for this tenant")

        # Generate short ID (idempotent: reuse if already set)
        short_id = brief.telegram_short_id
        if not short_id:
            short_id = secrets.token_urlsafe(6)[:8]
            brief.telegram_short_id = short_id

        redis_key = _BRIEF_SHORT_ID_KEY.format(short_id=short_id)
        await redis_client.setex(redis_key, _BRIEF_SHORT_ID_TTL, str(brief.id))

        bot_token = str(tg_config["bot_token"])
        chat_id = str(tg_config["chat_id"])
        provider = (
            get_telegram_provider(bot_token=bot_token, chat_id=chat_id)
            if bot_token.startswith("mock")
            else TelegramProvider(bot_token=bot_token, chat_id=chat_id)
        )
        result = await provider.send_brief_card(
            headline=brief.headline,
            angle=brief.angle,
            talking_points=brief.talking_points,
            tone=brief.tone_guidance,
            risk_level=brief.risk_level,
            risk_label=str(getattr(brief, "generation_trace", {}).get("risk_label", "low")),
            content_vertical=brief.content_vertical,
            why_now=brief.why_now,
            cta_strategy=brief.cta_strategy,
            platform_targets=brief.target_platforms,
            short_id=short_id,
        )
        # Store message_id for in-place editing after approve/reject
        if result.get("message_id"):
            brief.telegram_message_id = result["message_id"]
        await self.db.flush()
        return result

    async def get_by_short_id(self, short_id: str) -> EditorialBrief | None:
        """Look up a brief from its Redis short-ID (used by Telegram callback handler)."""
        return await self.repo.get_by_telegram_short_id(short_id)

    async def handle_telegram_brief_callback(self, payload: dict[str, Any]) -> None:
        """
        Handle gate-1 Telegram callback: approve_brief:<short_id> or reject_brief:<short_id>.
        Resolves the brief via short_id, transitions status, acks the callback, and edits the
        card message in-place to reflect the decision.
        """
        callback_query = payload.get("callback_query", {})
        if not callback_query:
            return

        callback_query_id = callback_query.get("id", "")
        data = callback_query.get("data", "")
        # Extract message context for in-place editing
        tg_message = callback_query.get("message", {})
        cb_message_id = str(tg_message.get("message_id", ""))
        cb_chat_id = str(tg_message.get("chat", {}).get("id", ""))

        is_valid, action, short_id = verify_signed_callback_data(data)
        if not is_valid:
            return

        brief = await self.get_by_short_id(short_id)
        if not brief or brief.status != BriefStatus.READY.value:
            return

        now = datetime.now(timezone.utc)
        if action == "approve_brief":
            brief.status = BriefStatus.APPROVED.value
            cluster = await self.story_repo.get_cluster(brief.tenant_id, brief.story_cluster_id)
            if cluster:
                cluster.workflow_state = TrendWorkflowState.APPROVED_TOPIC.value
            brief.actioned_at = now
            ack_text = "✅ Brief approved — content generation can proceed."
            edited_text = (
                f"<b>📋 Editorial Brief — ✅ APPROVED</b>\n\n"
                f"<b>Headline:</b> {brief.headline}\n"
                f"<b>Angle:</b> {brief.angle}"
            )
        elif action == "reject_brief":
            brief.status = BriefStatus.REJECTED.value
            cluster = await self.story_repo.get_cluster(brief.tenant_id, brief.story_cluster_id)
            if cluster:
                cluster.workflow_state = TrendWorkflowState.REJECTED.value
            brief.actioned_at = now
            ack_text = "❌ Brief rejected."
            edited_text = (
                f"<b>📋 Editorial Brief — ❌ REJECTED</b>\n\n"
                f"<b>Headline:</b> {brief.headline}\n"
                f"<b>Angle:</b> {brief.angle}"
            )
        elif action in {"safer_brief", "soften_brief", "text_only_brief", "text_video_brief"}:
            rewrite_mode = {
                "safer_brief": "safer_angle",
                "soften_brief": "soften",
                "text_only_brief": "text_only",
                "text_video_brief": "text_video",
            }[action]
            brief = await self.rewrite_brief(
                brief.tenant_id,
                brief.id,
                BriefRewriteRequest(mode=rewrite_mode),
                actor_user_id=None,
            )
            ack_text = "♻️ Brief rewritten."
            edited_text = (
                f"<b>📋 Editorial Brief — ♻️ REWRITTEN</b>\n\n"
                f"<b>Headline:</b> {brief.headline}\n"
                f"<b>Angle:</b> {brief.angle}\n"
                f"<b>Why now:</b> {brief.why_now}"
            )
        else:
            return

        await self.db.flush()

        # Ack the callback button press and edit the message in-place
        try:
            tg_config = await SettingsService(self.db).resolve_telegram_runtime_config(brief.tenant_id)
            bot_token = str(tg_config.get("bot_token", ""))
            chat_id = cb_chat_id or str(tg_config.get("chat_id", ""))
            if bot_token:
                provider = (
                    get_telegram_provider(bot_token=bot_token, chat_id=chat_id)
                    if bot_token.startswith("mock")
                    else TelegramProvider(bot_token=bot_token, chat_id=chat_id)
                )
                if callback_query_id:
                    await provider.answer_callback(callback_query_id, ack_text)
                # Edit the brief card in-place using the message_id from the callback
                edit_message_id = cb_message_id or brief.telegram_message_id
                if edit_message_id and chat_id:
                    await provider.edit_message(
                        chat_id=chat_id,
                        message_id=edit_message_id,
                        new_text=edited_text,
                    )
        except Exception:
            pass  # Ack/edit failure must not roll back status change
