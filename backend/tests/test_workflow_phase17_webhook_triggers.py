"""Phase 17 — workflow webhook / event trigger ingress."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.workflows.webhook_crypto import (
    sanitize_trigger_payload,
    stable_event_id,
    verify_generic_hmac,
)
from backend.modules.workflows.webhook_trigger_config import (
    normalize_webhook_trigger_config,
    parse_webhook_trigger_config,
)


def test_normalize_rejects_raw_secret_fields() -> None:
    with pytest.raises(ValueError, match="signing_secret_ref"):
        normalize_webhook_trigger_config({"endpoint_id": "abcdefghij"})
    with pytest.raises(ValueError, match="reference"):
        normalize_webhook_trigger_config(
            {
                "endpoint_id": "abcdefghij",
                "signing_secret_ref": "password=hunter2",
            }
        )


def test_normalize_strips_banned_secret_keys_and_keeps_ref() -> None:
    cfg = normalize_webhook_trigger_config(
        {
            "endpoint_id": "endpoint_abc123",
            "signing_secret_ref": "tenant.webhook.primary",
            "signing_secret": "SHOULD_NOT_PERSIST",
            "require_timestamp": False,
        }
    )
    assert cfg["signing_secret_ref"] == "tenant.webhook.primary"
    assert "signing_secret" not in cfg
    assert cfg["endpoint_id"] == "endpoint_abc123"


def test_hmac_with_timestamp() -> None:
    secret = "test-secret"
    body = b'{"hello":"world"}'
    ts = int(time.time())
    signed = f"{ts}.".encode() + body
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    assert (
        verify_generic_hmac(
            secret=secret,
            body=body,
            signature_header=f"sha256={digest}",
            timestamp=ts,
            max_skew_seconds=300,
            require_timestamp=True,
        )
        is True
    )
    assert (
        verify_generic_hmac(
            secret=secret,
            body=body,
            signature_header=f"sha256={digest}",
            timestamp=ts - 10_000,
            max_skew_seconds=300,
            require_timestamp=True,
        )
        is False
    )


def test_stable_event_id_prefers_idempotency_key() -> None:
    body = b"payload"
    a = stable_event_id(idempotency_key="evt-1", body=body)
    b = stable_event_id(idempotency_key="evt-1", body=b"other")
    c = stable_event_id(idempotency_key=None, body=body)
    assert a == b
    assert a != c


def test_sanitize_trigger_payload_drops_secret_keys() -> None:
    out = sanitize_trigger_payload({"text": "ok", "api_key": "sk", "nested": {"token": "x", "n": 1}})
    assert out["text"] == "ok"
    assert "api_key" not in out
    assert out["nested"] == {"n": 1}


def test_webhook_trigger_node_is_stable() -> None:
    from backend.modules.workflows.nodes.base import NodeImplementationStatus
    from backend.modules.workflows.registry import build_default_registry, reset_default_registry

    reset_default_registry(build_default_registry())
    node = build_default_registry().get("webhook_trigger")
    assert node is not None
    assert node.implementation_status is NodeImplementationStatus.STABLE
    assert node.is_executable() is True
    reset_default_registry(None)


def test_parse_config_defaults() -> None:
    cfg = parse_webhook_trigger_config(
        {
            "endpoint_id": "endpoint_xyz_99",
            "signing_secret_ref": "refs/webhook",
        }
    )
    assert cfg.signature_header == "X-SignalForge-Signature"
    assert cfg.require_timestamp is True


def test_receive_rejects_bad_signature() -> None:
    import asyncio

    from fastapi import HTTPException

    from backend.modules.workflows.webhook_ingress import receive_workflow_webhook

    async def _run() -> None:
        automation = MagicMock()
        automation.id = uuid.uuid4()
        automation.tenant_id = uuid.uuid4()
        automation.enabled = True
        automation.trigger_config = {
            "endpoint_id": "endpoint_test01",
            "signing_secret_ref": "ref.a",
            "require_timestamp": False,
        }
        db = AsyncMock()

        with (
            patch(
                "backend.modules.workflows.webhook_ingress.get_automation_by_endpoint",
                new=AsyncMock(return_value=automation),
            ),
            patch(
                "backend.modules.workflows.webhook_ingress.resolve_secret_reference",
                return_value="secret",
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await receive_workflow_webhook(
                db,
                endpoint_id="endpoint_test01",
                raw_body=b"{}",
                headers={"X-SignalForge-Signature": "sha256=deadbeef"},
                process_inline=True,
            )
        assert exc.value.status_code == 403

    asyncio.run(_run())


def test_receive_dedupes_existing_inbox() -> None:
    import asyncio

    from backend.modules.workflows.webhook_ingress import receive_workflow_webhook

    async def _run() -> None:
        automation = MagicMock()
        automation.id = uuid.uuid4()
        automation.tenant_id = uuid.uuid4()
        automation.enabled = True
        automation.trigger_config = {
            "endpoint_id": "endpoint_test01",
            "signing_secret_ref": "ref.a",
            "require_timestamp": False,
        }
        body = b'{"ok":true}'
        digest = hmac.new(b"secret", body, hashlib.sha256).hexdigest()

        existing = MagicMock()
        existing.id = uuid.uuid4()
        existing.status = "processed"
        existing.payload = {"workflow_run_id": str(uuid.uuid4())}

        repo = MagicMock()
        repo.get_webhook_by_dedupe_key = AsyncMock(return_value=existing)
        db = AsyncMock()

        with (
            patch(
                "backend.modules.workflows.webhook_ingress.get_automation_by_endpoint",
                new=AsyncMock(return_value=automation),
            ),
            patch(
                "backend.modules.workflows.webhook_ingress.resolve_secret_reference",
                return_value="secret",
            ),
            patch(
                "backend.modules.workflows.webhook_ingress._reserve_replay",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "backend.modules.workflows.webhook_ingress.ApprovalRepository",
                return_value=repo,
            ),
        ):
            result = await receive_workflow_webhook(
                db,
                endpoint_id="endpoint_test01",
                raw_body=body,
                headers={"X-SignalForge-Signature": f"sha256={digest}"},
                process_inline=False,
            )
        assert result["deduped"] is True
        assert result["inbox_id"] == str(existing.id)
        assert result["workflow_run_id"] == existing.payload["workflow_run_id"]

    asyncio.run(_run())


def test_process_inbox_idempotent_via_correlation() -> None:
    import asyncio

    from backend.modules.workflows.webhook_ingress import process_workflow_webhook_inbox

    async def _run() -> None:
        inbox_id = uuid.uuid4()
        automation_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        run_id = uuid.uuid4()

        inbox = MagicMock()
        inbox.id = inbox_id
        inbox.status = "received"
        inbox.dedupe_key = "wf:dedupe"
        inbox.payload = {
            "automation_id": str(automation_id),
            "event_id": "abc" * 10,
            "body_json": json.dumps({"hello": "world"}),
        }
        inbox.error_message = None

        automation = MagicMock()
        automation.id = automation_id
        automation.tenant_id = tenant_id
        automation.enabled = True
        automation.workflow_version_id = uuid.uuid4()
        automation.brand_id = None

        run = MagicMock()
        run.id = run_id

        repo = MagicMock()
        repo.get_pending_webhook = AsyncMock(return_value=inbox)

        db = AsyncMock()
        db.get = AsyncMock(return_value=automation)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        engine = MagicMock()
        engine.start_run = AsyncMock(return_value=run)

        with (
            patch(
                "backend.modules.workflows.webhook_ingress.ApprovalRepository",
                return_value=repo,
            ),
            patch(
                "backend.modules.workflows.webhook_ingress.WorkflowEngine",
                return_value=engine,
            ),
        ):
            first = await process_workflow_webhook_inbox(db, inbox_id=inbox_id)
            assert first["status"] == "processed"
            assert first["workflow_run_id"] == str(run_id)
            assert inbox.status == "processed"

            second = await process_workflow_webhook_inbox(db, inbox_id=inbox_id)
            assert second["status"] == "processed"
            assert engine.start_run.await_count == 1
            corr = engine.start_run.await_args.kwargs["correlation_id"]
            assert corr.startswith(f"wh:{automation_id}:")
            assert len(corr) <= 128

    asyncio.run(_run())
