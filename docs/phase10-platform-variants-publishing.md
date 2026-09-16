# Phase 10 — Connect Platform Transform to Actual Publishing

Critical gap closed: PlatformTransform no longer produces ephemeral-only variants.

## Flow

```text
Canonical content
  → PlatformTransform   # adapt once per fingerprint; persist ContentVariant
  → Approval (optional)
  → Publish             # provider input from durable variant snapshot
```

## Durable model

`ContentVariant` (content-generation domain — not a duplicate of GeneratedAsset):

* `tenant_id`, `content_job_id`, `workflow_run_id?`
* `fingerprint`, `platform`, `text`, `title`, `description`, `tags`, `media_refs`

`ContentVariantTarget` maps `variant_id → social_account_id`.

`GeneratedAsset` `TEXT_VARIANT` remains generation-time drafts. Workflow late specialization
uses `ContentVariant`.

## PublishingJob

* `content_variant_id` (nullable FK)
* `provider_payload` holds an **immutable snapshot** derived from the variant
  (`variant_source=content_variant`, `variant_text`, …)

Provider execution prefers the snapshot (or loaded variant) over GeneratedAsset text.

Clients cannot supply raw `provider_payload` via `PublishNowRequest`.

## Idempotency

When a variant is present, the key includes
`content_job_id + social_account_id + content_variant_id + schedule + intent + mode`.

## Wiring

* `PlatformTransform` persists when `content_job_id` + DB session are available;
  output includes `variant_ids`.
* `Publish` accepts `content_variant_ids`; legacy bag forwards `variant_ids` /
  `variants[].id`.
* Without explicit ids, publish still resolves variants by account target mapping.

## Migration

`a9b0c1d2e3f4_content_variants.py` (revises `f8a9b0c1d2e3`).
