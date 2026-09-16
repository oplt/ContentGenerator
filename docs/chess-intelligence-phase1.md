# Chess Intelligence — Phase 1 Domain Models

Canonical catalog for games/puzzles. Separate from `chess_video` (render only).

## Persist vs domain-only

| Concept | Decision | Why |
|---------|----------|-----|
| `ChessGame` | **SQL table** | Search, dedupe, famous catalog, video handoff |
| `ChessPuzzle` | **SQL table** | Browser, daily puzzle, bulk import |
| `ChessGameSource` | **Defer (Phase 5)** | Primary provenance on `ChessGame.source_*` for now; multi-source table when Lichess + archive collide |
| `ChessGameTag` | **JSON `historical_tags`** | Low cardinality editorial tags; no join table yet |
| `ChessEngineAnalysis` | **Defer (Phase 14)** | No Stockfish yet |
| `ChessCriticalMoment` | **SQL table** | Heuristic labels from engine facts (Phase 15) |
| `AnnotatedChessMove` | **Domain dataclass** | Derived on read; not stored |

## Moves storage trade-off

| Option | Idea | Verdict |
|--------|------|---------|
| **A** | Store `normalized_pgn`; derive plies with `python-chess` | **Chosen** |
| B | JSONB move list | Dupes PGN; drifts; large rows |
| C | `ChessGameMove` rows | Millions of rows at archive scale; no current query needs per-move SQL |

Access pattern today: validate → list/search games → feed PGN to video / (later) engine. Deriving ≤1000 plies in-process is cheap. `annotate_moves()` in `moves.py` exposes ply / side / SAN / UCI / FEN before+after without persistence.

Revisit Option B/C only if product needs SQL filters on intermediate FENs at catalog scale.

## Fingerprints

* `game_fingerprint` = sha256(`starting_fen|uci_moves|result`)
* `content_hash` = sha256(normalized PGN)
* Puzzle: `puzzle_fingerprint` = sha256(`starting_fen|solution_uci`)

Unique per tenant on fingerprint; partial unique on provider + external_id.

## Relationship to video

```text
chess_intelligence.ChessGame.normalized_pgn
        ↓
chess_video.create(source_text=...)
```

No FK required in Phase 1.

## Phase 2 — Provider interface

```text
HTTP JSON → provider adapter → External* DTO → normalizer → ChessGame/ChessPuzzle
```

* Protocols: `HistoricalGameProvider`, `PuzzleProvider` (`providers/base.py`)
* DTOs: `ChessGameSearchQuery`, `ExternalChessGame(Summary)`, `ExternalChessPuzzle`
* Normalize: `normalize_external_game` / `normalize_external_puzzle`
* Raw provider JSON must not cross the adapter boundary — only curated `source_metadata`

Concrete Lichess adapters = Phase 3+.

## Phase 3 — Lichess masters provider

Official Opening Explorer (OpenAPI `lichess-org/api`):

| Method | Path | Notes |
|--------|------|-------|
| GET | `{LICHESS_EXPLORER_BASE_URL}/masters` | `play` (UCI csv), `fen`, `since`, `until`, `topGames`≤15 |
| GET | `{LICHESS_EXPLORER_BASE_URL}/masters/pgn/{gameId}` | `application/x-chess-pgn` |

Default host: `https://explorer.lichess.org`. Optional `LICHESS_API_TOKEN` (Bearer). Upstream may 401 `/masters` without token; PGN often public. Token never exposed to frontend.

Impl: `LichessMastersProvider` — shared `core.http.request` (retry 429/transport only), local RPH limiter, health state, DTO mapping → `normalize_external_game`.

## Phase 4 — PGN archive import

Streaming importer (never load whole file):

```text
.pgn file → chess.pgn.read_game loop → parse_chess_input → fingerprint
         → batch dedupe vs DB → commit
```

* `importers/pgn_archive.py` — `PgnArchiveImporter`
* `repository.py` — fingerprint lookups / batch insert
* CLI: `python -m backend.scripts.import_chess_pgn --file … --tenant-id … [--provider] [--source-name] [--batch-size] [--dry-run] [--skip-games]`

Idempotent via `game_fingerprint`. Provenance in `source_metadata` (`source_name`, `archive_file`, `game_index`, `import_batch`).

## Phase 5 — Fingerprint + multi-source

Fingerprint (unchanged formula):

```text
sha256(starting_fen | " ".join(uci_moves) | result)
```

Player names excluded on purpose (spelling variance). `normalize_player_name()` exists for catalog matching only.

```text
ChessGame (1)
  ├── ChessGameSource lichess_masters
  ├── ChessGameSource pgn_mentor
  └── ChessGameSource …
```

* Table `chess_game_sources` (migration `e4f5a6b7c8d9`)
* `ChessGameDedupeService.upsert_game` — create-or-link
* Importer attaches source on fingerprint hit instead of ignoring sighting
* Denormalized `ChessGame.source_*` = primary (first) sighting

## Phase 6 — Famous game catalog

Editorial YAML (not scraped annotations):

`backend/modules/chess_intelligence/data/famous_games.yaml`

Match signals (multi-signal; names alone never enough):

```text
year (+ optional near-year)
normalized players / aliases
event tokens
uci_prefix (optional)
game_fingerprint (optional exact)
```

* `famous_catalog.py` — load / score / apply metadata
* `famous_service.py` — tenant batch apply
* CLI: `python -m backend.scripts.apply_famous_catalog --tenant-id … [--dry-run]`

On match: `is_famous`, `famous_title`, `historical_tags`, `source_metadata.famous_catalog_id`.

## Phase 7 — Lichess puzzles

Official site API (public):

| Method | Path |
|--------|------|
| GET | `{LICHESS_API_BASE_URL}/api/puzzle/daily` |
| GET | `{LICHESS_API_BASE_URL}/api/puzzle/{id}` |

`LichessPuzzlesProvider` maps `PuzzleAndGame` → `ExternalChessPuzzle` (`fen` + `solution`).  
Normalize with `normalize_external_puzzle` — python-chess validates solution (provider JSON never trusted raw).

## Phase 8 — Bulk Lichess puzzle dataset

Do **not** commit the multi-million-row dump. Download from https://database.lichess.org/#puzzles, then stream:

```text
.csv / .csv.gz / .csv.zst → decompress → CSV → validate → batch insert
```

* `importers/lichess_puzzles.py` — FEN before opponent move; `Moves[0]` = opponent; store player fen + `Moves[1:]`
* Idempotent on `(provider=lichess_puzzles, external_id=PuzzleId)`
* CLI filters: `--limit --min-rating --max-rating --themes --min-popularity --batch-size --dry-run`

```bash
cd backend && PYTHONPATH=.. .venv/bin/python -m backend.scripts.import_lichess_puzzles \
  --file /data/lichess_db_puzzle.csv.zst \
  --tenant-id <uuid> --limit 10000 --min-rating 1200 --batch-size 200
```

## Phase 9 — Chess.com provider

Optional PubAPI adapter for **modern online** games (not primary historical OTB):

| Method | Path |
|--------|------|
| GET | `{CHESSCOM_API_BASE_URL}/pub/player/{user}/games/archives` |
| GET | `{CHESSCOM_API_BASE_URL}/pub/player/{user}/games/{YYYY}/{MM}` |

* `ChessComProvider` implements `HistoricalGameProvider`
* `search_games` requires `query.player` (username); walks recent month archives
* `external_id` = `{username}/{YYYY}/{MM}/{game_key}` (live/daily id or uuid)
* Normalize with `normalize_external_game` — same `ChessGame` model as Lichess/PGN
* Config: `CHESSCOM_*` + `HTTP_PROVIDER_CHESSCOM_CONCURRENCY` (identify via User-Agent)

## Phase 10 — Search API

Tenant-scoped catalog under `/api/v1/chess` (`content:write`):

| Method | Path |
|--------|------|
| GET | `/chess/games` |
| GET | `/chess/games/famous` |
| GET | `/chess/games/{id}` |
| GET | `/chess/games/{id}/moves` |
| POST | `/chess/games/import` |
| GET | `/chess/puzzles` |
| GET | `/chess/puzzles/daily` |
| GET | `/chess/puzzles/{id}` |

* Cursor pagination (`limit` ≤ 100, `created_at DESC, id DESC`)
* Game filters: player / white / black / year / event / result / opening / ECO / famous / provider / ratings / tag
* Puzzle filters: rating / theme / opening / popularity / provider
* Search indexes: migration `e5f6a7b8c9d1`
* Daily puzzle: Lichess provider → upsert → canonical `ChessPuzzleResponse`

## Phase 11 — Chess video pipeline bridge

Catalog games reuse the **existing** chess-video stack (no second renderer):

```text
ChessGame.normalized_pgn → ChessVideoService.create() → Celery → render/encode
```

| Method | Path |
|--------|------|
| POST | `/chess/games/{game_id}/video` |
| POST | `/chess-videos` with `chess_game_id` (same contract) |

* `ChessVideoCreateRequest` accepts `source_text` **or** `chess_game_id`
* Defaults title/subtitle from famous title / players when unset
* Fingerprinting, cache reuse, retry, storage unchanged

## Phase 12 — Frontend chess workspace

Feature package (keep `ChessVideoPage` thin):

```text
frontend/src/api/chessData.ts          # catalog API
frontend/src/api/chessVideos.ts        # render jobs only
frontend/src/features/chess/           # panels, cards, hooks, board preview
```

* Catalog surfaces: search / famous / puzzles (Phase 13 splits Games vs Puzzles)
* `CreateVideoAction` → existing renderer (`/chess/games/{id}/video` or hand-off to Create)
* Do not grow `ChessVideoPage.tsx` with catalog logic — compose feature workspaces

## Phase 13 — Chess UI structure

Operational workspace tabs on the Chess page:

```text
Games (Search | Famous | Imported)
Puzzles (Browse | Daily)
Create Video
Preview
History
```

```text
frontend/src/features/chess/GamesWorkspace.tsx
frontend/src/features/chess/PuzzlesWorkspace.tsx
frontend/src/features/chess/video/   # Create / Preview / History
```

* `ChessVideoPage` stays an orchestrator (job state + tab wiring only)
* Catalog → Create still loads `normalized_pgn` (no manual copy)
* `ChessCatalogWorkspace` re-exports `GamesWorkspace` for compatibility

## Phase 14 — Stockfish integration

Engine analysis runs **only** in Celery (never inside request handlers).

```text
backend/modules/chess_intelligence/engine/
  base.py          # ChessEngine protocol + White-POV EngineScore
  scores.py        # cp/mate helpers (no cp↔mate arithmetic)
  stockfish.py     # popen_uci adapter (STOCKFISH_PATH binary)
  analyzer.py      # per-ply walk
```

| Method | Path |
|--------|------|
| POST | `/chess/games/{id}/analyze` → 202 + queue |
| GET | `/chess/games/{id}/analysis` |
| GET | `/chess/analysis/{job_id}` |

Config: `STOCKFISH_PATH`, `CHESS_ENGINE_DEPTH`, `CHESS_ENGINE_TIME_LIMIT`,
`CHESS_ENGINE_HASH_MB`, `CHESS_ENGINE_THREADS`.

**Score convention:** all `evaluation_*` / `mate_*` fields are **White's perspective**
(positive = White better). `evaluation_delta` is set only when both sides are
non-mate centipawn scores.

UI: `AnalyzeGameAction` on game details polls job status and shows ply eval / best move.

## Phase 15 — Critical moment detection

Deterministic heuristics run **after** Stockfish analysis (same Celery job). No LLM labels.

```text
engine_facts → classification → heuristic_summary
editorial_description = null (reserved)
```

Impl: `engine/critical_moments.py` → rows on `chess_critical_moments`.

Returned on analysis job payloads as `critical_moments[]`.

Classifications (subset): blunder, mistake, large_evaluation_swing, turning_point,
forced_mate, mate_threat, missed_win, sacrifice, opening_transition, endgame_transition.

## Phase 16 — Tactical pattern detection

High-confidence geometric/material detectors (no LLM):

```text
engine/tactical_patterns.py + tactical_detectors.py
→ chess_tactical_patterns (confidence + detection_method)
```

Implemented now: fork, pin, skewer, discovered_attack, double_attack, back_rank_mate,
smothered_mate, promotion, underpromotion, queen/rook/bishop/knight_sacrifice,
exchange_sacrifice.

Deferred (low confidence): deflection, decoy, zwischenzug.

Returned on analysis payloads as `tactical_patterns[]`.

## Phase 17 — Content opportunity score

Transparent 0–100 score from **explicit** components (no LLM):

| Component | Cap |
|-----------|-----|
| historical_significance | 20 |
| player_fame (ratings) | 10 |
| tactical_intensity | 18 |
| evaluation_swing | 16 |
| puzzle_suitability | 15 |
| video_suitability | 15 |
| date_relevance | 6 |

Impl: `content_opportunity.py` → `chess_content_opportunity_scores` (persisted after analysis).

| Method | Path |
|--------|------|
| GET | `/chess/games/{id}/content-score` |

Also embedded on analysis job as `content_opportunity`. UI: `ContentOpportunityPanel`.

## Phase 18 — Workflow integration

Chess games/puzzles are **domain signals** on the existing workflow engine (no separate chess orchestrator).

| Node type | Wraps |
|-----------|--------|
| `retrieve_chess_game` | Catalog game + PGN |
| `retrieve_chess_puzzle` | Puzzle by id or daily |
| `analyze_chess_game` | Stockfish job enqueue (`sync` for tests) |
| `select_critical_moment` | Top heuristic moments |
| `score_chess_content` | Content opportunity 0–100 |
| `generate_chess_narrative` | Deterministic scaffold (not LLM) |
| `generate_chess_video` | Existing renderer; accepts `chess_game_id` |

Example pipeline: retrieve → analyze → select moments → narrative → `generate_chess_video` → platform transform → approval → publish.

Code: `backend/modules/workflows/nodes/chess_*.py` (retrieve/analyze/narrative + video), registry via `nodes/__init__.py`. Palette category: **Chess**.

## Phase 19 — Source provenance

Mandatory trace for every externally sourced game/puzzle:

```text
provider · external id · source URL · retrieved_at · source_metadata
import_batch_id · license_note
```

| Layer | Storage |
|-------|---------|
| Game | `ChessGame.source_*` + `ChessGameSource` rows (multi-provider) |
| Puzzle | `provider` / `external_id` + `retrieved_at` / `import_batch_id` / `license_note` |
| Video | `chess_video_jobs.chess_game_id` → catalog → sources → PGN |

| Method | Path |
|--------|------|
| GET | `/chess/games/{id}/provenance` |
| GET | `/chess/puzzles/{id}/provenance` |
| GET | `/chess-videos/{id}/provenance` |

Source evidence (PGN/FEN/solution) is authoritative — narrative/LLM copy must not replace it.

Impl: `licenses.py`, `provenance_service.py`, migration `f1a2b3c4d5e7`. UI: `ProvenancePanel`.

## Phase 20 — External source rules

Conservative integration only:

| Source | Allowed path | Forbidden |
|--------|--------------|-----------|
| Lichess | Documented Opening Explorer / site puzzle API + rate limits | HTML scrape |
| Lichess puzzle dump | Operator downloads `.csv.zst` → stream import (not in Git) | Committing the dump |
| Chess.com | Published Data API + rate limits | Undocumented scrape |
| PGN archives | Local permitted `.pgn` file import | Aggressive download scrapers |
| Chessgames.com etc. | Editorial research links only | Automated scrape of annotations |
| Famous games | SignalForge `famous_games.yaml` | Copying proprietary commentary |

Policy module: `source_rules.py` (`assert_provider_allowed_for_ingest`, bulk/live checks, forbidden hosts).
Wired into catalog import + PGN/puzzle importers. `.gitignore` excludes puzzle dumps / archive dirs.

## Phase 21 — HTTP reliability

Chess providers use `backend.core.http.request` (shared client, provider semaphore, Retry-After, transport backoff).

| Concern | Implementation |
|---------|----------------|
| Timeouts | `LICHESS_HTTP_TIMEOUT_SECONDS` / `CHESSCOM_HTTP_TIMEOUT_SECONDS` via `build_timeout` |
| Retries | `*_HTTP_MAX_RETRIES` + core 429/transport retry |
| Rate limit | Local RPH limiter + upstream 429 → `ChessProviderRateLimitedError` |
| Auth failure | 401/403 → `ChessProviderAuthError` |
| Not found | 404 → `ChessProviderNotFoundError` |
| Unavailable | timeout/5xx → `ChessProviderUnavailableError` |
| Invalid payload | shape/PGN gaps → `ChessProviderInvalidResponseError` / `ChessParseError` |
| DB failure | mapped to HTTP 500 `"Database failure"` (no SQL/stack to client) |

Safe HTTP mapping: `providers/http_errors.py`. Structured logs include `code` + `retryable`. Metrics via existing `cg` provider request/retry/429 series.

## Phase 22 — Cache strategy

Reuse TenantCache / Redis (`OWNER_CHESS` = `chess_intelligence`). No second cache stack.

| Concern | Behavior |
|---------|----------|
| Canonical catalog game/puzzle | Serve from DB — no external refetch |
| Masters search | Moderate TTL (~30m) |
| Historical / month PGN | Long TTL (~7d) |
| Daily puzzle | Expire near next UTC midnight |
| Individual puzzle | Long TTL (~7d) |
| Provider metadata (archives) | ~1h TTL |

Impl: `providers/provider_cache.py`, wired into Lichess masters/puzzles + Chess.com. Prefer-catalog helper: `catalog_prefer.py`.

## Phase 23 — Database migrations

All chess persistent models are Alembic-owned. **Do not** use `create_all` for production schema.

| Revision | Adds |
|----------|------|
| `e3f4a5b6c7d8` | `chess_games`, `chess_puzzles` + fingerprint / provider-external uniques |
| `e4f5a6b7c8d9` | `chess_game_sources` + FKs |
| `e5f6a7b8c9d1` | Search indexes |
| `f7a8b9c0d1e2` | Analysis jobs + position analyses |
| `f8a9b0c1d2e4` | Critical moments |
| `f9a0b1c2d3e4` | Tactical patterns |
| `f0a1b2c3d4e6` | Content opportunity scores |
| `f1a2b3c4d5e7` | Puzzle provenance cols + `chess_video_jobs.chess_game_id` FK |
| `f2a3b4c5d6e8` | Soft-delete-aware fingerprint partial uniques |

Guarantees: tenant FKs (`ON DELETE CASCADE`), game/job FKs, provider+external_id uniqueness (partial), fingerprint uniqueness where `deleted_at IS NULL`. Head must remain a single linear chain for existing deployments (`alembic upgrade head`).

## Phase 24 — Async jobs

Long-running chess work runs on Celery with persisted progress (not HTTP request lifetime).

| Job | Mechanism |
|-----|-----------|
| Stockfish analysis | `ChessAnalysisJob` + `analyze_chess_game_task` (video/media queue) |
| PGN archive import | `ChessCatalogJob` kind `pgn_import` |
| Bulk puzzle import | kind `puzzle_import` |
| Famous-game enrichment | kind `enrich_famous` |
| Critical-moment re-extract | kind `extract_critical_moments` (from stored plies) |
| Provider sync | kind `provider_sync` (Lichess masters / Chess.com → catalog) |

Catalog jobs: table `chess_catalog_jobs` (migration `f3a4b5c6d7e9`), worker `run_chess_catalog_job_task` (ingestion queue, `acks_late`, dedupe-idempotent). Progress + `result` counters flush after each import batch.

API:

| Method | Path |
|--------|------|
| POST | `/chess/jobs` (202) |
| GET | `/chess/jobs/{id}` |

## Phase 25 — Testing

Backend areas covered (see `test_chess_phase25_coverage.py`):

| Area | Owning tests |
|------|----------------|
| Lichess parsing / PGN retrieval | `test_lichess_*` |
| Provider errors | `test_chess_provider_http_reliability` |
| Archive streaming | `test_pgn_archive_import` |
| Normalize / fingerprint / dedupe | domain + dedupe + providers |
| Famous matching | `test_famous_catalog` |
| Puzzle parse / illegal solution | puzzles + `test_normalize_rejects_illegal_puzzle_solution` |
| Search + pagination | `test_chess_search_api` |
| Tenant isolation | `test_chess_tenant_isolation` |
| Video handoff | `test_chess_game_video_bridge` |
| Stockfish scores / critical moments | stockfish + critical_moments |

Frontend focused tests live under `frontend/src/features/chess/*.test.tsx` (search, famous, puzzles, moves, details, video bridge). Page-level smoke remains in `ChessVideoPage.test.tsx`. HTTP is mocked; unit tests do not require internet.

## Phase 26 — Dependency policy

Reuse platform deps; Stockfish stays an **external binary** (`STOCKFISH_PATH`), not a PyPI engine package.

See [`chess-dependency-policy.md`](./chess-dependency-policy.md). Guard: `tests/test_chess_dependency_policy.py`.

## Phase 27 — Backend structure

Suggested tree adopted and extended (providers / importers / engine / data). Celery stays in `workers/task_defs/`.

Canonical map: [`chess-backend-structure.md`](./chess-backend-structure.md). Guard: `tests/test_chess_backend_structure.py`.

## Phase 28 — Frontend structure

API: `chessData.ts` + `chessVideos.ts`. UI: `features/chess/*` (panels, viewers, video tabs). Page shell remains `ChessVideoPage` at `/dashboard/chess-video` (rename deferred).

Canonical map: [`chess-frontend-structure.md`](./chess-frontend-structure.md).

## Phase 29 — UX requirements

Dashboard patterns: tabs, cards, filters, dialogs, list skeletons, empty/error states, tooltips. Game search framed as research/content selection (★ Famous cards, View / Analyze / Create video).

Canonical notes: [`chess-ux-requirements.md`](./chess-ux-requirements.md).

## Phase 30 — Configuration

Chess settings live in `backend/.env.example` / `Settings` (Lichess, Chess.com, cache TTLs, Stockfish). No unified `CHESS_PROVIDER_TIMEOUT_SECONDS` — use per-provider timeouts. Provider secrets never go through Vite.

Canonical notes: [`chess-configuration.md`](./chess-configuration.md). Guard: `tests/test_chess_configuration.py`.

## Phase 31 — Observability

Structured logs for provider request/latency/errors, import counts (games/puzzle), engine analysis duration/failure, and video handoff. Metrics: `cg.chess.import.total` + `cg.operation.*` / existing `cg.provider.*`.

Canonical notes: [`chess-observability.md`](./chess-observability.md). Guard: `tests/test_chess_observability.py`.

## Phase 32 — Documentation

Operator/developer guide covering providers, configuration, imports, provenance, famous catalog, Stockfish, APIs, frontend, and game→video — with example commands.

Canonical entry: [`chess.md`](./chess.md). Guard: `tests/test_chess_documentation.py`.
