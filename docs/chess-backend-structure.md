# Chess intelligence — backend structure (Phase 27)

Prompt Phase 27 suggested a minimal tree. After inspecting modular-monolith
conventions (`modules/<domain>/` + `workers/task_defs/` for Celery), that
layout is **adopted and extended** — not flattened or renamed for purity.

## Boundary

| Package | Owns |
|---------|------|
| `backend.modules.chess_intelligence` | Canonical games/puzzles, providers, importers, engine analysis, catalog jobs, provenance |
| `backend.modules.chess_video` | Render/encode jobs only (consumes catalog PGN / `chess_game_id`) |
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
├── service.py                # catalog CRUD / daily puzzle
├── analysis_service.py
├── content_score_service.py
├── catalog_job_service.py
├── famous_service.py
├── provenance_service.py
├── router.py
├── provenance_router.py
├── catalog_job_router.py
├── normalizer.py
├── fingerprint.py
├── moves.py
├── dedupe.py
├── licenses.py
├── source_rules.py
├── catalog_prefer.py
├── content_opportunity.py
├── analysis_persist.py
├── famous_catalog.py
├── catalog_job_runners.py
├── catalog_job_sync.py
│
├── providers/
│   ├── __init__.py
│   ├── base.py               # protocols + error types
│   ├── dtos.py
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
├── chess_analysis.py         # Stockfish job
├── chess_catalog.py          # import / enrich / sync jobs
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
