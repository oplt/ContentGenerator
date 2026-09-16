# Phase 11 — Canonical Content Model

Separate raw AI ops from durable editorial artifacts.

## Artifact layers

| Layer | Representation | Node / service |
|-------|----------------|----------------|
| Raw AI | ephemeral text | `generate_text` |
| Editorial | `ContentJob` | `generate_canonical_content` → `ContentGenerationService` |
| Platform | `ContentVariant` | `platform_transform` (Phase 10) |
| Distribution | `PublishingJob` | `publish` |

## Recommended flow

```text
Research / content plan
  → generate_canonical_content   # ContentJob + policies
  → (media nodes)
  → approval
  → platform_transform           # ContentVariant
  → publish                      # PublishingJob
```

`generate_text` remains a low-level reusable LLM node. It does **not** create a
ContentJob and must not re-implement brand, risk, prompt, or persistence policy.

## `generate_canonical_content`

* Input: `content_plan_id` (+ optional accounts / feedback / revision)
* Calls existing `ContentGenerationService.generate` (approved brief, orchestrator,
  asset persistence, risk grounding)
* Output: `content_job_id`, `text` (canonical body), `status`, `risk_label`, …
* Stamps `grounding_bundle["canonical_text"]` for downstream nodes

## PlatformTransform

May resolve canonical body from `content_job_id` when `text` is omitted
(`grounding_bundle.canonical_text` or writer/text assets via
`content_generation.canonical.extract_canonical_text`).

## Helpers

* `backend/modules/content_generation/canonical.py`
* `backend/modules/workflows/nodes/canonical_content.py`
