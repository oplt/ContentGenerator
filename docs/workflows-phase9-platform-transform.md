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
* Output: `canonical_text`, `variants[]` (`platform`, `fingerprint`, `text`, account ids)

Platform rules (deterministic):

| Platform | Behavior |
|----------|----------|
| X | ≤280, optional hashtags if they fit |
| Instagram | ≤1000 + hashtag block |
| LinkedIn | ≤3000 + light hashtags |
| YouTube | title ≤95, description ≤1000 + tags |
| other | platform limit or 1000 |

Accounts resolved from input ids, else `context_snapshot.accounts`.

## Modules

* `platform_adapt.py`
* `nodes/platform_transform.py`
* `engine_inputs` maps `text`/`variants` → transform/publish

## Next

Phase 10 — typed platform capability model.
