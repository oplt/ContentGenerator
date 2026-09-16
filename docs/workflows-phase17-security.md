# Workflow Domain — Phase 17 (Security)

## Controls in place

| Requirement | Mechanism |
|-------------|-----------|
| Tenant isolation | Composite FKs + every repo query takes `tenant_id` |
| Authz read/write | Membership for reads; `content:write` for mutations |
| Account selection | `authorize_social_account_ids` → `assert_accounts_authorized` on automation targets |
| Credentials | Live only in `SocialAccountToken` (encrypted); never in graph JSON |
| Graph secret scrub | `sanitize_workflow_graph` on draft save + publish |
| Automation JSON scrub | `sanitize_mapping` on settings/trigger_config/overrides |
| Approval callbacks | Existing HMAC/signing + webhook dedupe in approvals module |
| Publish idempotency | `wf-publish-{run_id}` + unique job keys |
| Audit | definition create, version publish, run start, automation create/enable/targets, approval decisions, social account upsert |

## Audit actions

* `workflows.definition_created`
* `workflows.version_published`
* `workflows.run_started`
* `automations.created` / `automations.enabled_changed` / `automations.targets_changed`
* `approvals.decision`
* `publishing.account_upserted`

## Frontend contract

Nodes/APIs expose `social_account_id` only — never OAuth/refresh tokens.

## Deferred

Workflow-owned signed webhook ingress (`WebhookTriggerNode` stub). External wait resumes stay behind authenticated `/workflows/resume`. Approval channel webhooks remain the signed external path.
