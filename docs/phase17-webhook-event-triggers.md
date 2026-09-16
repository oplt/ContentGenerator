# Phase 17 — Webhook / Event Triggers

Signed automation webhooks start workflow runs without session auth.

## Endpoint

```http
POST /api/v1/workflows/webhooks/{endpoint_id}
```

* No JWT — HMAC required
* Global + per-endpoint rate limits
* Body size capped (256 KiB)
* Looks up `Automation.webhook_endpoint_id` for `trigger_type` in `{webhook, event}`

## Secrets

* Automation `trigger_config.signing_secret_ref` is a **reference id** only
* Resolved via `EXTERNAL_SECRET_REFERENCES_JSON` → `resolve_secret_reference`
* Raw fields (`signing_secret`, `secret`, …) are stripped on create/update
* Never stored in `WorkflowVersion.graph_json` — `webhook_trigger` node config may only hold an optional `expected_endpoint_id` label

## Signature

Default provider: generic HMAC-SHA256

* Header: `X-SignalForge-Signature: sha256=<hex>` (or Stripe-like `t=,v1=`)
* Signed payload: `{unix_ts}.{raw_body}` when `require_timestamp` (default true)
* Timestamp header: `X-SignalForge-Timestamp`
* Skew window: `max_skew_seconds` (default 300)

## Dedup / replay / idempotency

1. Redis NX key `wf_webhook_replay:{endpoint_id}:{event_id}` (skew TTL)
2. `WebhookInbox` unique `dedupe_key` = `wf:{tenant_id}:{endpoint_id}:{event_id}`
3. `WorkflowRun.correlation_id` = `wh:{automation_id}:{event_id}` (≤128 chars) → `start_run` returns existing run

`event_id` prefers `X-Idempotency-Key`, else SHA-256 of body.

## Processing

1. Verify signature → write `WebhookInbox` (`provider=workflow_webhook`)
2. Celery `process_workflow_webhook_inbox_task` (or inline when `WORKFLOW_INLINE_NODE_EXECUTION`)
3. Sanitize payload (`strip_secrets`) → `WorkflowEngine.start_run(trigger_type=webhook)`

## Graph node

`webhook_trigger` is **stable** / executable. Echoes sanitized ingress payload on ports `payload` / `trigger_type`.

## Migration

`c1d2e3f4a5b6` — `automations.webhook_endpoint_id` (unique when set).
