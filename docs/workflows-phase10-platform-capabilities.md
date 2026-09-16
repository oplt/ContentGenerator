# Workflow Domain — Phase 10 (Platform Capability Model)

Typed capabilities for compile-time account/platform checks — no big-bang enum migration.

## Model

`backend/modules/publishing/platform_capabilities.py`

```text
PlatformCapabilities
  supports_text / images / video / audio / threads / native_scheduling
  max_text_length / max_images / max_video_*
  supported_*_formats
  provider_id (string)
  raw_flags (legacy SocialAccount.capability_flags)
```

Bridge:

* `flags_to_capabilities(flags, platform=...)` — merge provider flags onto string-id defaults
* `workflow_capability_tags(caps)` — node `required_capabilities` tags (`video`, `image`, `tts`, …)
* Runtime overlays: `llm`, `publish` (SignalForge, not platform-native)

Defaults keyed by provider string (`x`, `youtube`, `instagram`, …) — not a global enum of all platforms.

## Compile context

`CompileContext` fields:

* `account_capabilities` — string tags (existing)
* `account_platform_capabilities` — typed dumps
* `account_platforms` — account_id → provider id
* `require_capability_check` — hard-fail when caps unresolved

`capability_context.enrich_compile_context*` fills maps from platform/flags or DB accounts before validate/start.

## Compiler rules

* No selected accounts → soft-skip (draft graphs OK)
* Selected accounts + resolved caps → require node capabilities ⊆ union of account tags
* Media nodes (`video` / `image` / `tts` / …) with unresolved caps → `unknown_capabilities` (or when `require_capability_check`)
* Soft tag: `chess` (product feature; still requires `video` from platform)

Example: video node + X-only account → `incompatible_capabilities` before any generation.

## Wiring

* Engine `start_run` enriches from DB then validates
* Config snapshots store `platform_capabilities` beside `capability_flags`
* `platform_adapt` uses typed `max_text_length` when flags/platform known

## Non-goals

* Migrating `SocialAccount.capability_flags` column away
* Replacing provider `capabilities()` return type (still `dict[str, str]`)
* Hardcoding every future platform into an enum
