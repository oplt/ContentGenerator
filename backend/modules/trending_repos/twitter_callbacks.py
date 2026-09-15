"""Telegram callbacks for Twitter post approve/edit/reject flows."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def handle_twitter_post_callback(
    callback_query: dict,
    db: "AsyncSession",
) -> None:
    """
    Handle tw_post / tw_edit / tw_reject inline button callbacks from Telegram.
    Always calls answerCallbackQuery to dismiss the loading spinner.
    """
    import json as _json

    from backend.core.cache import redis_client
    from backend.modules.approvals.providers import (
        get_telegram_provider,
        verify_signed_callback_data,
    )
    from backend.modules.trending_repos.service import TrendingReposService

    callback_data: str = callback_query.get("data", "")
    callback_query_id: str = str(callback_query.get("id", ""))
    # chat_id from the incoming message (used for edit session key)
    incoming_chat_id: str = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))
    message_id: str = str(callback_query.get("message", {}).get("message_id", ""))

    valid, action, post_id = verify_signed_callback_data(callback_data)

    redis_key = f"twitter_post:{post_id}" if post_id else ""
    raw = await redis_client.get(redis_key) if redis_key else None

    if not raw:
        if valid and not raw:
            logger.warning("Twitter post callback: Redis key missing for post_id=%s", post_id)
        return

    stored = _json.loads(raw)
    tenant_id = uuid.UUID(stored["tenant_id"])
    post_text: str = stored["post_text"]
    bot_token: str = stored.get("bot_token", "")
    chat_id: str = stored.get("chat_id", incoming_chat_id)

    provider = get_telegram_provider(bot_token=bot_token, chat_id=chat_id)

    if not valid:
        await provider.answer_callback(callback_query_id, "⚠️ Invalid request signature.")
        return

    if action == "tw_post":
        await redis_client.delete(redis_key)
        try:
            svc = TrendingReposService(db)
            await svc._post_to_twitter_for_tenant(tenant_id, post_text)
            await provider.answer_callback(callback_query_id, "✅ Posted to Twitter!")
            await provider.edit_message(
                chat_id=chat_id,
                message_id=message_id,
                new_text=f"<b>✅ Posted to Twitter</b>\n\n{post_text}",
            )
        except Exception:
            logger.exception("Failed to post to Twitter from Telegram callback")
            await provider.answer_callback(callback_query_id, "❌ Failed to post.")

    elif action == "tw_reject":
        await redis_client.delete(redis_key)
        await provider.answer_callback(callback_query_id, "❌ Post rejected.")
        await provider.edit_message(
            chat_id=chat_id,
            message_id=message_id,
            new_text=f"<b>❌ Rejected</b>\n\n<s>{post_text}</s>",
        )

    elif action == "tw_edit":
        edit_session_key = f"twitter_post:edit_session:{incoming_chat_id}"
        await redis_client.set(edit_session_key, post_id, ex=3600)
        await provider.answer_callback(callback_query_id, "✏️ Send your updated post text now.")


async def handle_twitter_edit_message(
    payload: dict[str, Any],
    db: "AsyncSession",
) -> bool:
    """
    If a Twitter edit session is active for this chat, apply the incoming message
    as the new post text and re-send the card with updated content.
    Returns True if the message was consumed.
    """
    import json as _json

    from backend.core.cache import redis_client
    from backend.modules.approvals.providers import get_telegram_provider
    from backend.modules.settings.service import SettingsService

    message = payload.get("message", {})
    text = message.get("text", "").strip()
    chat_id = str(message.get("chat", {}).get("id", ""))
    if not text or not chat_id:
        return False

    edit_session_key = f"twitter_post:edit_session:{chat_id}"
    post_id = await redis_client.get(edit_session_key)
    if not post_id:
        return False

    redis_key = f"twitter_post:{post_id}"
    raw = await redis_client.get(redis_key)
    if not raw:
        await redis_client.delete(edit_session_key)
        return False

    stored = _json.loads(raw)
    tenant_id = uuid.UUID(stored["tenant_id"])
    repo_name: str = stored.get("repo_full_name", "")
    repo_url: str = stored.get("repo_url", "")

    # Update stored post text
    stored["post_text"] = text
    await redis_client.set(redis_key, _json.dumps(stored), ex=86400)
    await redis_client.delete(edit_session_key)

    # Re-send the card with the new text
    svc_settings = SettingsService(db)
    config = await svc_settings.resolve_telegram_runtime_config(tenant_id)
    bot_token = str(config.get("bot_token") or "")
    telegram_chat_id = str(config.get("chat_id") or "")
    provider = get_telegram_provider(bot_token=bot_token, chat_id=telegram_chat_id)
    await provider.send_twitter_post_card(
        repo_name=repo_name,
        repo_url=repo_url,
        post_text=text,
        post_id=post_id,
    )
    return True
