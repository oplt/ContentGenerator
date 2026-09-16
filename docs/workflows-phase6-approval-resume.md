# Workflow Domain — Phase 6 (Durable Approval / Waiting)

Human approvals pause workflows without holding Celery workers.

## Flow

```text
Generate → ApprovalNode
            ↓
   ApprovalRequest (pending)
   WorkflowNodeRun = WAITING + resume_token
   WorkflowRun = WAITING
   (no worker active)
            ↓
 Telegram / WhatsApp / in-app action
            ↓
   apply_intent → maybe_resume_workflow_from_approval
            ↓
   node SUCCEEDED|FAILED → unlock → advance
```

## Binding

`ApprovalRequest.response_payload_json["workflow"]` holds:

* `resume_token`
* `workflow_run_id` / `workflow_node_run_id` / `node_id`
* `on_timeout` (`stop` | `continue`)
* `channels` (metadata; delivery stays in ApprovalService)

Engine pre-mints `resume_token` before `may_pause` nodes execute so ApprovalNode can stamp the binding.

## Publish ownership

Workflow-bound approvals **do not** auto-`publish_now` on approve. `PublishNode` owns publishing.

## API

* `POST /api/v1/workflows/resume` — `{resume_token, outcome, decision?, advance?}`
* Existing approval channels (`operator_action`, Telegram/WhatsApp) resume via hook
* Expire task marks `expired` then resumes (`on_timeout=stop` → FAILED)

## Outcomes

| Outcome | Node | Run (typical) |
|---------|------|----------------|
| approved | SUCCEEDED + unlock | advance downstream |
| rejected | FAILED | FAILED |
| expired + stop | FAILED | FAILED |
| expired + continue | SUCCEEDED (timed_out) | advance |

## Next

Phase 7 — DB-backed automation scheduler.
