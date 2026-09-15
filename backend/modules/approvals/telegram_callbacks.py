"""Telegram inline-keyboard callback orchestration (Gate 2 — asset approval)."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.approvals.models import ApprovalMessage, ApprovalRequest
from backend.modules.approvals.providers import (
    TelegramProvider,
    get_telegram_provider,
    verify_signed_callback_data,
)
from backend.modules.approvals.telegram_callback_intents import dispatch_intent
from backend.modules.approvals.telegram_messages import (
    handle_telegram_message as handle_telegram_message,
)


class _TelegramDeps(Protocol):
    db: AsyncSession
    repo: Any
    settings_service: Any
    audit: Any
    content_repo: Any
    content_service: Any
    story_repo: Any

    async def _record_callback_failure(
        self, request: ApprovalRequest | None, *, callback_data: str, reason: str
    ) -> None: ...
    async def _apply_intent(
        self, request: ApprovalRequest, intent: str, feedback: str | None
    ) -> None: ...
    async def send_publish_for_approval(self, **kwargs: Any) -> ApprovalRequest: ...


async def _resolve_telegram_chat(
    svc: Any, request: ApprovalRequest, cb_chat_id: str
) -> tuple[str, str]:
    try:
        telegram_config = await svc.settings_service.resolve_telegram_runtime_config(
            request.tenant_id
        )
        bot_token = str(telegram_config.get("bot_token", ""))
        chat_id = cb_chat_id or str(telegram_config.get("chat_id", ""))
    except Exception:
        bot_token = ""
        chat_id = cb_chat_id
    return bot_token, chat_id


async def _ack_and_edit_card(
    *,
    bot_token: str,
    chat_id: str,
    callback_query_id: str,
    ack_text: str,
    edited_text: str | None,
    edit_message_id: str | None,
) -> None:
    if not bot_token:
        return
    try:
        provider = (
            get_telegram_provider(bot_token=bot_token, chat_id=chat_id)
            if not bot_token or bot_token.startswith("mock")
            else TelegramProvider(bot_token=bot_token, chat_id=chat_id)
        )
        if callback_query_id:
            await provider.answer_callback(callback_query_id, ack_text)
        if edit_message_id and chat_id and edited_text:
            await provider.edit_message(
                chat_id=chat_id,
                message_id=edit_message_id,
                new_text=edited_text,
            )
    except Exception:
        # Ack/edit failure must not roll back the approval state change.
        pass


async def handle_telegram_callback(svc: Any, payload: dict[str, Any]) -> None:
    """
    Process an inline keyboard callback_query from Telegram.
    Acks the popup, applies intent, edits the approval card in-place.
    """
    callback_query = payload.get("callback_query")
    if not callback_query:
        return

    callback_query_id = callback_query.get("id", "")
    data = callback_query.get("data", "")
    tg_message = callback_query.get("message", {})
    cb_message_id = str(tg_message.get("message_id", ""))
    cb_chat_id = str(tg_message.get("chat", {}).get("id", ""))

    is_valid, intent_str, request_id_str = verify_signed_callback_data(data)
    request: ApprovalRequest | None = None
    try:
        request = await svc.repo.get_request_by_id(UUID(request_id_str))
    except ValueError:
        pass

    if not is_valid:
        await svc._record_callback_failure(request, callback_data=data, reason="invalid_signature")
        await svc.db.commit()
        return
    if not request:
        return

    bot_token, chat_id = await _resolve_telegram_chat(svc, request, cb_chat_id)
    outcome = await dispatch_intent(
        svc,
        request,
        intent_str=intent_str,
        chat_id=chat_id,
        cb_chat_id=cb_chat_id,
    )
    if outcome is None:
        return

    await svc.repo.create_message(
        ApprovalMessage(
            approval_request_id=request.id,
            direction="inbound",
            channel="telegram",
            message_type="callback",
            raw_text=data,
            parsed_intent=intent_str,
            intent_confidence=1.0,
            payload={"callback_data": data, "chat_id": cb_chat_id, "message_id": cb_message_id},
        )
    )
    request.responded_by = f"telegram:{cb_chat_id}" if cb_chat_id else "telegram"

    await _ack_and_edit_card(
        bot_token=bot_token,
        chat_id=chat_id,
        callback_query_id=callback_query_id,
        ack_text=outcome.ack_text,
        edited_text=outcome.edited_text,
        edit_message_id=cb_message_id or request.telegram_message_id,
    )

    await svc.audit.record(
        tenant_id=request.tenant_id,
        actor_user_id=None,
        action="approvals.telegram_callback",
        entity_type="approval_request",
        entity_id=str(request.id),
        message=f"Telegram callback: {intent_str}",
        payload={"intent": intent_str, "approval_type": request.approval_type},
        payload_schema="approval.telegram_callback.v1",
    )
    await svc.db.commit()
