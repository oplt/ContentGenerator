# Chess intelligence — backend structure (Phase 27)

Prompt Phase 27 suggested a minimal tree. After inspecting modular-monolith
conventions (`modules/<domain>/` + `workers/task_defs/` for Celery), that
layout is **adopted and extended** — not flattened or renamed for purity.

## Boundary

| Package | Owns |
|---------|------|
| `backend.modules.chess_intelligence` | Canonical games/puzzles, providers, importers, engine analysis, catalog jobs, provenance |
| `backend.modules.chess_video` | Render/encode only (§22 downstream of catalog; no provider ingestion) |
| `backend.workers.task_defs.chess_*` | Celery entrypoints (thin; call domain services) |

Domain logic stays out of API routers; HTTP adapters stay under `providers/`.

## Finalized tree

```text
backend/modules/chess_intelligence/
├── __init__.py
├── models.py                 # games, puzzles, analysis, moments, scores
├── catalog_job_models.py     # async catalog jobs (Phase 24; line-budget split)
├── schemas.py
├── catalog_job_schemas.py
├── repository.py
├── catalog_queries.py        # filtered search + cursor pagination
├── catalog_concepts.py       # famous ≠ recent/notable ≠ content opportunity (§8)
├── service.py                # catalog CRUD / daily puzzle
├── analysis_service.py       # Stockfish enqueue + fingerprint reuse (§12)
├── analysis_fingerprint.py   # deterministic analysis identity (≠ job id)
├── analysis_history.py       # §14: latest / preferred / matching selection
├── analysis_persist.py
├── content_score_service.py
├── catalog_job_service.py
├── famous_service.py
├── provenance_service.py
├── router.py
├── provenance_router.py
├── catalog_job_router.py
├── normalizer.py
├── fingerprint.py            # starting_fen|uci|result identity (§17)
├── moves.py
├── dedupe.py                 # fingerprint upsert + multi-source attach (§16)
├── historical_assets.py      # durable historical PGN policy (no scheduled redownload)
├── operational_catalog.py    # §18 selective import filters + caps (not a warehouse)
├── puzzle_catalog.py         # §19 ChessPuzzle scope (≠ historical games)
├── import_manifest.py        # archive checksum embed into catalog jobs (no new table)
├── ingestion_mode.py         # hybrid lifecycle modes (bootstrap/discovery/…)
├── schema_changes.py         # §27 hybrid schema inventory (sync state + fingerprint)
├── idempotency.py            # §28 concurrency/idempotency contracts + DB guarantees
├── failure_semantics.py      # §29 provider/engine/archive failures ≠ catalog erase
├── provider_sync_state.py    # durable feed checkpoints (≠ ChessCatalogJob runs)
├── licenses.py
├── source_rules.py           # IntegrationMode: how providers may be contacted
├── catalog_prefer.py
├── content_opportunity.py
├── discovery_eligibility.py  # §21: cheap gates before optional Stockfish on discovery
├── famous_catalog.py
├── famous_service.py
├── famous_policy.py          # fame = editorial on ChessGame; no FamousGame table / no PGN fetch
├── admin_sync.py             # §25 admin job actions vs browse GET separation
├── operational_runbook.py    # §33 ops → CLI / jobs / APIs (no new shell scripts)
├── external_service_security.py  # §34 credentials / scrape / famous / narrative
├── performance.py            # §35 indexes / streaming / sync bounds / Stockfish off HTTP
├── scope_v1.py               # §36 modular monolith; forbid Kafka/ES/microservice/lake
├── target_architecture.py    # §37 concept → file owners (no diagram-only folders)
├── priority_order.py         # §38 P0→P4 delivery checklist + owners
├── acceptance_criteria.py    # §39 critical ✓ checklist + evidence map
├── local_first.py            # §9: user-facing GETs → local DB only (no live providers)
├── daily_freshness.py        # §10: daily GET freshness / is_stale metadata
├── catalog_schedule.py       # §11/§26: cadence policy + config-driven beat (no bulk reanalyze)
├── catalog_job_runners.py
├── catalog_job_sync.py       # provider_sync + §21 optional analyze fan-out
│
├── providers/
│   ├── __init__.py
│   ├── base.py               # protocols + error types
│   ├── dtos.py               # ExternalChess* only (not canonical ChessGame)
│   ├── registry.py           # §15: get_historical_game_provider / get_puzzle_provider
│   ├── boundary.py           # §15: forbidden domain-import scan policy
│   ├── http_errors.py
│   ├── provider_cache.py     # TenantCache TTLs (Phase 22)
│   ├── lichess_http.py
│   ├── lichess_masters.py
│   ├── lichess_puzzles.py
│   ├── chesscom_http.py
│   └── chesscom.py
│
├── importers/
│   ├── __init__.py
│   ├── pgn_archive.py
│   └── lichess_puzzles.py
│
├── engine/
│   ├── __init__.py
│   ├── base.py
│   ├── stockfish.py          # external STOCKFISH_PATH binary
│   ├── analyzer.py
│   ├── scores.py
│   ├── critical_moments.py
│   ├── tactical_patterns.py
│   └── tactical_detectors.py
│
└── data/
    └── famous_games.yaml

backend/workers/task_defs/
├── chess_analysis.py         # Stockfish job (on demand)
├── chess_catalog.py          # run job + daily/provider fanouts (§11)
└── chess_video.py            # render (chess_video module)
```

## Suggested → actual

| Phase 27 suggestion | Status |
|---------------------|--------|
| Core models/schemas/repo/service/router | Present |
| `normalizer` / `fingerprint` | Present |
| `providers/` Lichess + Chess.com | Present (+ shared HTTP + cache) |
| `importers/` PGN + puzzles | Present |
| `engine/` Stockfish + critical moments | Present (+ scores, tactics) |
| `data/famous_games.yaml` | Present |
| Provenance / content opportunity / catalog jobs | Added (phases 17–24) as sibling modules, not nested under `providers/` |

No further reshuffle required unless a file exceeds the line budget — then split by responsibility (as with `catalog_job_*` and `engine/tactical_*`).
