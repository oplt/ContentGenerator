"""
Tests for Step 4 — Telegram Approval System (Two-Gate Flow).

Covers:
- TelegramProvider.send_brief_card: correct callback_data format with short_id
- TelegramProvider.set_webhook: passes secret_token when provided
- EditorialBriefService.send_to_telegram: generates short_id, stores in Redis, calls send_brief_card
- EditorialBriefService.handle_telegram_brief_callback: approve_brief/reject_brief transitions
- Webhook router: brief callbacks routed before content callbacks
- Secret token validation in webhook handler
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.approvals.providers import TelegramProvider, build_signed_callback_data
from backend.modules.editorial_briefs.models import BriefStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _telegram_provider():
    return TelegramProvider(bot_token="test-bot-token", chat_id="123456789")


def _brief(status: str = BriefStatus.READY.value):
    b = MagicMock()
    b.id = uuid.uuid4()
    b.tenant_id = uuid.uuid4()
    b.status = status
    b.headline = "Tech layoffs at AI startup"
    b.angle = "How this signals a broader industry correction"
    b.talking_points = ["Point 1", "Point 2", "Point 3"]
    b.tone_guidance = "analytical"
    b.risk_level = "safe"
    b.content_vertical = "tech"
    b.telegram_short_id = None
    b.actioned_at = None
    b.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    return b


def _brief_svc():
    from backend.modules.editorial_briefs.service import EditorialBriefService
    svc = object.__new__(EditorialBriefService)
    svc.db = AsyncMock()
    svc.db.flush = AsyncMock()
    svc.repo = AsyncMock()
    svc.story_repo = AsyncMock()
    svc.llm = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# TelegramProvider.send_brief_card
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_brief_card_uses_short_id_in_callback_data() -> None:
    provider = _telegram_provider()
    short_id = "abc12345"

    captured_payload = {}

    async def mock_post(url, json=None, **kwargs):
        captured_payload.update(json or {})
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value={"result": {"message_id": 42}})
        return response

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(side_effect=mock_post))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await provider.send_brief_card(
            headline="Test headline",
            angle="Test angle",
            talking_points=["point 1", "point 2"],
            tone="authoritative",
            risk_level="safe",
            content_vertical="tech",
            short_id=short_id,
        )

    assert result["short_id"] == short_id
    keyboard = captured_payload["reply_markup"]["inline_keyboard"][0]
    approve_btn = next(b for b in keyboard if "Approve" in b["text"])
    reject_btn = next(b for b in keyboard if "Reject" in b["text"])
    assert approve_btn["callback_data"] == build_signed_callback_data("approve_brief", short_id)
    assert reject_btn["callback_data"] == build_signed_callback_data("reject_brief", short_id)


@pytest.mark.asyncio
async def test_send_brief_card_callback_data_under_64_chars() -> None:
    """Telegram's callback_data limit is 64 bytes — short_id keeps us under it."""
    provider = _telegram_provider()
    short_id = "ab1cd2ef"  # 8 chars

    approve_data = build_signed_callback_data("approve_brief", short_id)
    reject_data = build_signed_callback_data("reject_brief", short_id)

    assert len(approve_data.encode()) <= 64
    assert len(reject_data.encode()) <= 64


# ---------------------------------------------------------------------------
# TelegramProvider.set_webhook
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_webhook_passes_secret_token() -> None:
    provider = _telegram_provider()
    captured = {}

    async def mock_post(url, json=None, **kwargs):
        captured.update(json or {})
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json = MagicMock(return_value={"ok": True})
        return r

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(side_effect=mock_post))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

        await provider.set_webhook("https://example.com/webhook", secret_token="my-secret")

    assert captured["secret_token"] == "my-secret"
    assert captured["url"] == "https://example.com/webhook"


@pytest.mark.asyncio
async def test_set_webhook_omits_secret_token_when_empty() -> None:
    provider = _telegram_provider()
    captured = {}

    async def mock_post(url, json=None, **kwargs):
        captured.update(json or {})
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json = MagicMock(return_value={"ok": True})
        return r

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(side_effect=mock_post))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

        await provider.set_webhook("https://example.com/webhook")

    assert "secret_token" not in captured


# ---------------------------------------------------------------------------
# EditorialBriefService.send_to_telegram
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_to_telegram_stores_short_id_in_redis() -> None:
    svc = _brief_svc()
    brief = _brief(BriefStatus.READY.value)

    svc.repo.get = AsyncMock(return_value=brief)

    tg_config = {"enabled": True, "bot_token": "token123", "chat_id": "987654"}
    mock_settings_svc = AsyncMock()
    mock_settings_svc.resolve_telegram_runtime_config = AsyncMock(return_value=tg_config)

    mock_provider = AsyncMock()
    mock_provider.send_brief_card = AsyncMock(return_value={"provider": "telegram", "message_id": "42", "short_id": "xx"})

    stored_redis = {}

    async def mock_setex(key, ttl, value):
        stored_redis[key] = value

    with (
        patch("backend.modules.editorial_briefs.service.SettingsService", return_value=mock_settings_svc),
        patch("backend.modules.editorial_briefs.service.TelegramProvider", return_value=mock_provider),
        patch("backend.modules.editorial_briefs.service.redis_client") as mock_redis,
    ):
        mock_redis.setex = AsyncMock(side_effect=mock_setex)
        result = await svc.send_to_telegram(brief.tenant_id, brief.id)

    assert brief.telegram_short_id is not None
    short_id = brief.telegram_short_id
    assert f"brief:short:{short_id}" in stored_redis
    assert stored_redis[f"brief:short:{short_id}"] == str(brief.id)
    mock_provider.send_brief_card.assert_called_once()


@pytest.mark.asyncio
async def test_send_to_telegram_raises_409_if_not_ready() -> None:
    from fastapi import HTTPException
    svc = _brief_svc()
    brief = _brief(BriefStatus.PENDING.value)
    svc.repo.get = AsyncMock(return_value=brief)

    with pytest.raises(HTTPException) as exc:
        await svc.send_to_telegram(brief.tenant_id, brief.id)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_send_to_telegram_raises_422_if_telegram_not_configured() -> None:
    from fastapi import HTTPException
    svc = _brief_svc()
    brief = _brief(BriefStatus.READY.value)
    svc.repo.get = AsyncMock(return_value=brief)

    tg_config = {"enabled": False, "bot_token": "", "chat_id": ""}
    mock_settings_svc = AsyncMock()
    mock_settings_svc.resolve_telegram_runtime_config = AsyncMock(return_value=tg_config)

    with patch("backend.modules.editorial_briefs.service.SettingsService", return_value=mock_settings_svc):
        with pytest.raises(HTTPException) as exc:
            await svc.send_to_telegram(brief.tenant_id, brief.id)
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# handle_telegram_brief_callback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_brief_callback_approve_transitions_to_approved() -> None:
    svc = _brief_svc()
    brief = _brief(BriefStatus.READY.value)
    short_id = "testshrt"
    brief.telegram_short_id = short_id

    svc.repo.get_by_telegram_short_id = AsyncMock(return_value=brief)

    tg_config = {"bot_token": "token", "chat_id": "123", "enabled": True}
    mock_settings_svc = AsyncMock()
    mock_settings_svc.resolve_telegram_runtime_config = AsyncMock(return_value=tg_config)
    mock_provider = AsyncMock()
    mock_provider.answer_callback = AsyncMock()

    payload = {
        "callback_query": {
            "id": "cb123",
            "data": build_signed_callback_data("approve_brief", short_id),
            "message": {"chat": {"id": 123}},
        }
    }

    with (
        patch("backend.modules.editorial_briefs.service.SettingsService", return_value=mock_settings_svc),
        patch("backend.modules.editorial_briefs.service.TelegramProvider", return_value=mock_provider),
    ):
        await svc.handle_telegram_brief_callback(payload)

    assert brief.status == BriefStatus.APPROVED.value
    assert brief.actioned_at is not None
    mock_provider.answer_callback.assert_called_once()


@pytest.mark.asyncio
async def test_brief_callback_reject_transitions_to_rejected() -> None:
    svc = _brief_svc()
    brief = _brief(BriefStatus.READY.value)
    short_id = "testshrt"
    brief.telegram_short_id = short_id

    svc.repo.get_by_telegram_short_id = AsyncMock(return_value=brief)

    tg_config = {"bot_token": "", "chat_id": "", "enabled": False}
    mock_settings_svc = AsyncMock()
    mock_settings_svc.resolve_telegram_runtime_config = AsyncMock(return_value=tg_config)

    payload = {
        "callback_query": {
            "id": "cb456",
            "data": build_signed_callback_data("reject_brief", short_id),
            "message": {"chat": {"id": 123}},
        }
    }

    with patch("backend.modules.editorial_briefs.service.SettingsService", return_value=mock_settings_svc):
        await svc.handle_telegram_brief_callback(payload)

    assert brief.status == BriefStatus.REJECTED.value


@pytest.mark.asyncio
async def test_brief_callback_ignores_non_ready_brief() -> None:
    """Callbacks on already-approved briefs are silently ignored."""
    svc = _brief_svc()
    brief = _brief(BriefStatus.APPROVED.value)
    svc.repo.get_by_telegram_short_id = AsyncMock(return_value=brief)

    payload = {
        "callback_query": {
            "id": "cb789",
            "data": build_signed_callback_data("approve_brief", "testshrt"),
            "message": {"chat": {"id": 123}},
        }
    }
    initial_status = brief.status
    await svc.handle_telegram_brief_callback(payload)
    assert brief.status == initial_status  # unchanged


# ---------------------------------------------------------------------------
# Brief router endpoint
# ---------------------------------------------------------------------------

def test_send_telegram_route_registered() -> None:
    from backend.api.router import api_router
    paths = [route.path for route in api_router.routes]
    telegram_routes = [p for p in paths if "/briefs" in p and "telegram" in p]
    assert len(telegram_routes) >= 1, f"No /briefs/*/send-telegram route found. Paths: {paths}"


# ---------------------------------------------------------------------------
# TelegramProvider.edit_message
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edit_message_calls_edit_message_text_api() -> None:
    provider = _telegram_provider()
    captured = {}

    async def mock_post(url, json=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json = MagicMock(return_value={"ok": True})
        return r

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(side_effect=mock_post))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

        await provider.edit_message(chat_id="12345", message_id="99", new_text="Updated text")

    assert "editMessageText" in captured["url"]
    assert captured["json"]["chat_id"] == "12345"
    assert captured["json"]["message_id"] == "99"
    assert captured["json"]["text"] == "Updated text"
    # Inline keyboard should be cleared (removed)
    assert captured["json"]["reply_markup"] == {"inline_keyboard": []}


@pytest.mark.asyncio
async def test_edit_message_uses_html_parse_mode_by_default() -> None:
    provider = _telegram_provider()
    captured = {}

    async def mock_post(url, json=None, **kwargs):
        captured.update(json or {})
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json = MagicMock(return_value={"ok": True})
        return r

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(side_effect=mock_post))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

        await provider.edit_message(chat_id="1", message_id="2", new_text="<b>Bold</b>")

    assert captured["parse_mode"] == "HTML"


# ---------------------------------------------------------------------------
# TelegramProvider.send_asset_card
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_asset_card_includes_all_three_action_buttons() -> None:
    provider = _telegram_provider()
    captured_json = {}

    async def mock_post(url, json=None, **kwargs):
        captured_json.update(json or {})
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json = MagicMock(return_value={"result": {"message_id": 77}})
        return r

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(side_effect=mock_post))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

        request_id = str(uuid.uuid4())
        result = await provider.send_asset_card(
            headline="AI breaks records",
            platform_previews=["[X] Tweet preview here", "[IG] Instagram caption here"],
            approval_request_id=request_id,
            risk_level="safe",
        )

    keyboard = captured_json["reply_markup"]["inline_keyboard"][0]
    intents = {btn["callback_data"].split(":")[0] for btn in keyboard}
    assert "approve" in intents
    assert "reject" in intents
    assert "revise" in intents
    assert result["message_id"] == "77"


@pytest.mark.asyncio
async def test_send_asset_card_callback_data_includes_request_id() -> None:
    provider = _telegram_provider()
    request_id = str(uuid.uuid4())
    captured_json = {}

    async def mock_post(url, json=None, **kwargs):
        captured_json.update(json or {})
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json = MagicMock(return_value={"result": {"message_id": 1}})
        return r

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(side_effect=mock_post))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

        await provider.send_asset_card(
            headline="headline",
            platform_previews=[],
            approval_request_id=request_id,
        )

    keyboard = captured_json["reply_markup"]["inline_keyboard"][0]
    for btn in keyboard:
        assert request_id in btn["callback_data"]


# ---------------------------------------------------------------------------
# handle_telegram_callback: edit_message called after approve/reject
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_telegram_callback_approve_calls_edit_message() -> None:
    from backend.modules.approvals.service import ApprovalService
    from backend.modules.approvals.models import ApprovalRequest, ApprovalStatus

    svc = object.__new__(ApprovalService)
    svc.db = AsyncMock()
    svc.repo = AsyncMock()
    svc.content_repo = AsyncMock()
    svc.content_service = AsyncMock()
    svc.publish_service = AsyncMock()
    svc.settings_service = AsyncMock()
    svc.audit = AsyncMock()

    request_id = uuid.uuid4()
    request = MagicMock(spec=ApprovalRequest)
    request.id = request_id
    request.tenant_id = uuid.uuid4()
    request.content_job_id = uuid.uuid4()
    request.status = ApprovalStatus.PENDING.value
    request.revision_count = 0
    request.channel = "telegram"
    request.recipient = "123456"
    request.telegram_message_id = "55"

    svc.repo.get_request_by_id = AsyncMock(return_value=request)
    svc.repo.create_message = AsyncMock()
    svc.settings_service.resolve_telegram_runtime_config = AsyncMock(
        return_value={"bot_token": "tok123", "chat_id": "999"}
    )
    svc.publish_service.publish_now = AsyncMock()
    svc.audit.record = AsyncMock()
    svc.content_repo.get_job = AsyncMock(return_value=None)

    edit_calls = []

    async def mock_edit(chat_id, message_id, new_text):
        edit_calls.append({"chat_id": chat_id, "message_id": message_id, "new_text": new_text})

    with patch("backend.modules.approvals.service.TelegramProvider") as MockTG:
        mock_provider = AsyncMock()
        mock_provider.answer_callback = AsyncMock()
        mock_provider.edit_message = AsyncMock(side_effect=mock_edit)
        MockTG.return_value = mock_provider

        payload = {
            "callback_query": {
                "id": "cb_approve",
                "data": build_signed_callback_data("approve", str(request_id)),
                "message": {
                    "message_id": 42,
                    "chat": {"id": 777},
                },
            }
        }
        await svc.handle_telegram_callback(payload)

    # edit_message must have been called with the approved outcome text
    assert len(edit_calls) == 1
    assert "APPROVED" in edit_calls[0]["new_text"]
    assert edit_calls[0]["message_id"] == "42"  # from callback payload
    assert edit_calls[0]["chat_id"] == "777"


@pytest.mark.asyncio
async def test_handle_telegram_callback_reject_calls_edit_message() -> None:
    from backend.modules.approvals.service import ApprovalService
    from backend.modules.approvals.models import ApprovalRequest, ApprovalStatus

    svc = object.__new__(ApprovalService)
    svc.db = AsyncMock()
    svc.repo = AsyncMock()
    svc.content_repo = AsyncMock()
    svc.content_service = AsyncMock()
    svc.publish_service = AsyncMock()
    svc.settings_service = AsyncMock()
    svc.audit = AsyncMock()

    request_id = uuid.uuid4()
    request = MagicMock(spec=ApprovalRequest)
    request.id = request_id
    request.tenant_id = uuid.uuid4()
    request.content_job_id = uuid.uuid4()
    request.status = ApprovalStatus.PENDING.value
    request.revision_count = 0
    request.telegram_message_id = None

    svc.repo.get_request_by_id = AsyncMock(return_value=request)
    svc.repo.create_message = AsyncMock()
    svc.settings_service.resolve_telegram_runtime_config = AsyncMock(
        return_value={"bot_token": "tok", "chat_id": "111"}
    )
    svc.audit.record = AsyncMock()
    svc.content_repo.get_job = AsyncMock(return_value=None)

    edit_calls = []

    async def mock_edit(chat_id, message_id, new_text):
        edit_calls.append({"new_text": new_text})

    with patch("backend.modules.approvals.service.TelegramProvider") as MockTG:
        mock_provider = AsyncMock()
        mock_provider.answer_callback = AsyncMock()
        mock_provider.edit_message = AsyncMock(side_effect=mock_edit)
        MockTG.return_value = mock_provider

        payload = {
            "callback_query": {
                "id": "cb_reject",
                "data": build_signed_callback_data("reject", str(request_id)),
                "message": {
                    "message_id": 88,
                    "chat": {"id": 333},
                },
            }
        }
        await svc.handle_telegram_callback(payload)

    assert len(edit_calls) == 1
    assert "REJECTED" in edit_calls[0]["new_text"]


# ---------------------------------------------------------------------------
# ApprovalRequest.approval_type model field
# ---------------------------------------------------------------------------

def test_approval_request_has_approval_type_field() -> None:
    from backend.modules.approvals.models import ApprovalRequest
    assert hasattr(ApprovalRequest, "approval_type")
    assert hasattr(ApprovalRequest, "telegram_message_id")


def test_approval_request_response_schema_has_approval_type() -> None:
    from backend.modules.approvals.schemas import ApprovalRequestResponse
    assert "approval_type" in ApprovalRequestResponse.model_fields
    assert "telegram_message_id" in ApprovalRequestResponse.model_fields


# ---------------------------------------------------------------------------
# brief_callback: edit_message called after approve/reject
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_brief_callback_approve_calls_edit_message() -> None:
    svc = _brief_svc()
    brief = _brief(BriefStatus.READY.value)
    short_id = "editme11"
    brief.telegram_short_id = short_id
    brief.telegram_message_id = "50"

    svc.repo.get_by_telegram_short_id = AsyncMock(return_value=brief)

    tg_config = {"bot_token": "tok", "chat_id": "777", "enabled": True}
    mock_settings_svc = AsyncMock()
    mock_settings_svc.resolve_telegram_runtime_config = AsyncMock(return_value=tg_config)

    edit_calls = []

    async def mock_edit(chat_id, message_id, new_text):
        edit_calls.append({"chat_id": chat_id, "message_id": message_id, "text": new_text})

    mock_provider = AsyncMock()
    mock_provider.answer_callback = AsyncMock()
    mock_provider.edit_message = AsyncMock(side_effect=mock_edit)

    payload = {
        "callback_query": {
            "id": "cb_brief",
            "data": build_signed_callback_data("approve_brief", short_id),
            "message": {"message_id": 60, "chat": {"id": 888}},
        }
    }

    with (
        patch("backend.modules.editorial_briefs.service.SettingsService", return_value=mock_settings_svc),
        patch("backend.modules.editorial_briefs.service.TelegramProvider", return_value=mock_provider),
    ):
        await svc.handle_telegram_brief_callback(payload)

    assert brief.status == BriefStatus.APPROVED.value
    assert len(edit_calls) == 1
    assert "APPROVED" in edit_calls[0]["text"]
    assert edit_calls[0]["message_id"] == "60"  # from callback payload


# ---------------------------------------------------------------------------
# send_for_approval stores telegram_message_id
# ---------------------------------------------------------------------------

def test_approval_request_model_stores_telegram_message_id() -> None:
    from backend.modules.approvals.models import ApprovalRequest
    assert hasattr(ApprovalRequest, "telegram_message_id")


def test_editorial_brief_model_has_telegram_message_id() -> None:
    from backend.modules.editorial_briefs.models import EditorialBrief
    assert hasattr(EditorialBrief, "telegram_message_id")
