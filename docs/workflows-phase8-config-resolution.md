# Workflow Domain — Phase 8 (Configuration Resolution)

Deterministic config precedence, frozen into `WorkflowRun.context_snapshot`.

## Precedence (later wins)

1. Node defaults (`ConfigSchema`)
2. Workflow `node.config`
3. Brand / BrandProfile editorial
4. Automation `settings.config` / `editorial` / `node_overrides`
5. Social-account (`AutomationTarget.overrides_json`, `BrandSocialAccount.generation_overrides`, …)
6. Explicit run/trigger params (`initial_inputs.config`, `trigger_payload.config`, `run_config`)

Key alias: `max_length` → `max_tokens`.

## Snapshot (no secrets)

Frozen at `start_run`:

* `resolved_node_configs` — per-node final config
* `resolved_editorial` — brand/profile merge
* `brand` / `brand_profile` / `automation` / `accounts` (+ `variant_fingerprint`)
* `providers` — names/models only (`LLM_PROVIDER`, `LLM_MODEL`)
* `run_params`, `config_precedence`, `graph_checksum`

Secret-looking keys (`token`, `api_key`, `password`, …) stripped.

## Modules

* `config_merge.py` — deep merge / strip / aliases
* `config_layers.py` — load + layer extract
* `config_snapshots.py` — sanitized snapshot fragments
* `config_resolver.py` — `ConfigResolver.build_snapshot` / `resolve_node_config`

Engine executes nodes with `snapshot.resolved_node_configs[node_id]` (not live graph/brand).

## Next

Phase 9 — canonical content + late platform specialization.
