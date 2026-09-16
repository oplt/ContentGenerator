# Workflow Domain — Phase 9 (Canonical Content + Late Platform Specialization)

Generate editorial copy **once**, then adapt per `variant_fingerprint` — never per account.

## Flow

```text
manual_trigger
  → generate_text          # canonical editorial body
  → platform_transform     # one variant per fingerprint group
  → approval (optional)
  → publish                # jobs still per account; shared fingerprint text
```

`fan_out` graph branching stays Phase 12. Publish already fans `PublishingJob`s by account.

## PlatformTransform

* Input: canonical `text` (+ optional `title` / `hashtags` / account ids)
* Groups targets via `group_by_fingerprint` (`publishing/account_selection.py`)
* Adapts with `platform_adapt.py` using `PLATFORM_LIMITS` (no LLM)
* Output: `canonical_text`, `variants[]` (`id?`, `platform`, `fingerprint`, `text`, account ids),
  `variant_ids[]` when persisted

Platform rules (deterministic):

| Platform | Behavior |
|----------|----------|
| X | ≤280, optional hashtags if they fit |
| Instagram | ≤1000 + hashtag block |
| LinkedIn | ≤3000 + light hashtags |
| YouTube | title ≤95, description ≤1000 + tags |
| other | platform limit or 1000 |

Accounts resolved from input ids, else `context_snapshot.accounts`.

## Persistence (production gap Phase 10)

When `content_job_id` + DB are present, variants are written as durable
`ContentVariant` (+ `ContentVariantTarget`) rows. Publish consumes those rows /
provider_payload snapshots — see [phase10-platform-variants-publishing.md](phase10-platform-variants-publishing.md).

Canonical body may be loaded from the ContentJob when `text` is omitted
([phase11-canonical-content-model.md](phase11-canonical-content-model.md)).

## Modules

* `platform_adapt.py`
* `nodes/platform_transform.py`
* `content_generation/variant_store.py`
* `engine_inputs` maps `text`/`variants`/`variant_ids` → transform/publish
