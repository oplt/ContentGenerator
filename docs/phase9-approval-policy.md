# Phase 9 — Approval Policy and Revision Semantics

Preserve WAITING/resume. Fix policy semantics.

## 9.1 `required=false`

Convention: **SUCCEEDED** with `status: "not_required"`.

Does not create an ApprovalRequest or durable wait. Downstream nodes (e.g. Publish)
still unlock. Prefer this over SKIPPED so approval placement rules and bag
routing keep a successful approval-shaped output (`content_job_id` included).

## 9.2 Channels

`ApprovalDeliveryService.deliver(request, channels)` sends only configured channels:

* `in_app` — create request; no outbound provider call
* `telegram` — existing Telegram asset card
* `whatsapp` — existing WhatsApp provider

`ApprovalNode` creates the request via `send_for_approval(..., deliver=False)` then
delivers. Standalone `/approvals` still uses default channel delivery inside
`send_for_approval`.

## 9.3 Revision binding

`response_payload_json["workflow"]` is preserved across revise/regenerate:

* `stamp_workflow_binding` / `merge_payload_preserving_workflow`
* `_apply_revise` re-stamps after re-send
* Telegram trim/CTA no longer wipes the binding when setting `revision_mode`
* `allow_revision=false` rejects revise intents

## 9.4 Approved revision identity

On approve, resume decision includes the **final**:

* `content_job_id`
* `approval_request_id`
* `revision_count`
* `status`

Publish must consume these from the approval node output bag.

## 9.5 Timeout

Approval WAITING persists a `WorkflowWait` (event + `wake_at`) via Phase 5.
Celery ETA is a fast wake only. On timeout wake, the ApprovalRequest is marked
`expired` when still pending.

## Tests

`tests/test_workflow_phase9_approval_policy.py`
