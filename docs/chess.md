# Chess in SignalForge

Operator and developer guide for the chess vertical: catalog intelligence
(`chess_intelligence`) plus match video rendering (`chess_video`).

UI entry: **Chess** → `/dashboard/chess-video` (page shell `ChessVideoPage`).

## Topics

| Topic | This guide | Deep dive |
|-------|------------|-----------|
| Supported providers | below | [source rules](./chess-intelligence-phase1.md) |
| Configuration | below | [`chess-configuration.md`](./chess-configuration.md) |
| Historical game import | below | Phase notes in [`chess-intelligence-phase1.md`](./chess-intelligence-phase1.md) |
| Puzzle import | below | same |
| Source provenance | below | same |
| Famous-game catalog | below | `data/famous_games.yaml` |
| Stockfish setup | below | [`chess-dependency-policy.md`](./chess-dependency-policy.md) |
| API routes | below | OpenAPI `/docs` |
| Frontend workflow | below | [`chess-frontend-structure.md`](./chess-frontend-structure.md), [`chess-ux-requirements.md`](./chess-ux-requirements.md) |
| Game → video | below | [`chess-video.md`](./chess-video.md) |
| Observability | — | [`chess-observability.md`](./chess-observability.md) |
| Backend layout | — | [`chess-backend-structure.md`](./chess-backend-structure.md) |
| Hybrid architecture | below | this guide §32 |
| Security / external services | below | this guide §34 |
| Performance | below | this guide §35 |
| Scope / anti-overengineering | below | this guide §36 |
| Target architecture | below | this guide §37 |
| Priority order | below | this guide §38 |
| Acceptance criteria | below | this guide §39 |

---

## Hybrid architecture (§32)

Local Postgres is the **system of record**. External APIs and archives are
**ingest only** — browse/search GETs never call providers.

```text
           EXTERNAL SOURCES
   ┌──────────┼───────────┐
   ↓          ↓           ↓
Lichess    PGN archives  Future APIs
   │          │           │
   └──────────┼───────────┘
              ↓
     Provider / Import Layer
              ↓
        Normalization
              ↓
       Fingerprint/Dedupe
              ↓
     LOCAL CANONICAL CATALOG
       │       │        │
       ↓       ↓        ↓
    Famous   Recent   Puzzles
       │       │
       │       ↓
       │   Stockfish
       │       ↓
       │ Critical Moments
       │       ↓
       │ Content Opportunity
       └───────┬────────
               ↓
       SignalForge Workflow
               ↓
          Chess Video
               ↓
        Review / Publish
```

### Concept distinctions

| Concept | What it is | What it is not |
|---------|------------|----------------|
| **Provider** | Adapter that talks to Lichess / Chess.com / archive files (`providers/*`, importers) | Canonical identity or UI client |
| **Source** | One provenance sighting (`ChessGameSource` + denormalized `source_*`) | The game itself |
| **Canonical game** | Fingerprint-deduped `ChessGame` row (SoT for PGN / search / video) | Provider external ID |
| **Famous curation** | Editorial metadata on an existing game (`is_famous`, YAML catalog) | A separate PGN store or scheduled redownload |
| **Recent discovery** | Incremental `provider_sync` into local catalog | Auto-fame or live browse proxy |
| **Content opportunity** | Score / reasons after (optional) analysis | Import filter or warehouse mandate |
| **Analysis profile** | Engine + depth + settings → `analysis_fingerprint` | Job UUID or provider cache key |
| **Sync checkpoint** | Durable `ChessProviderSyncState` (`high_water_mark`, lookback) | One `ChessCatalogJob` run |

UI maps Famous / Recent / Puzzles / Opportunity / Create Video / Analysis onto
existing panels — see [`chess-frontend-structure.md`](./chess-frontend-structure.md).

---

## Security + external-service rules (§34)

| Rule | Practice |
|------|----------|
| Credentials | `LICHESS_API_TOKEN`, Stockfish path, rate limits = **backend Settings only** — never Vite |
| Provider terms | Documented APIs only (`source_rules.PROVIDER_RULES`) |
| Rate limits | `LICHESS_RATE_LIMIT_RPH` / `CHESSCOM_RATE_LIMIT_RPH` + `HTTP_PROVIDER_*_CONCURRENCY` |
| Licensing | `licenses.py` → `license_note` on games / puzzles / sources |
| Attribution | Provenance panel + source URLs / external IDs |
| Source rules | Forbidden scrape hosts (`chessgames.com`, …); no curated-site HTML scrapers |
| No commentary scrape | Do not ingest proprietary annotations/comments |
| Facts vs narrative | Catalog PGN + provenance are factual; SignalForge briefs/publish stay separate |
| Famous catalog | SignalForge YAML metadata only — no silent copy of third-party annotations |

Contract: `external_service_security.py` (builds on `source_rules` + `licenses` +
`famous_catalog`). Config notes: [`chess-configuration.md`](./chess-configuration.md).

---

## Performance (§35)

| Rule | Practice |
|------|----------|
| No N+1 providers | Browse/search GETs are local-first (`local_first.py`) |
| Search = Postgres | `ChessCatalogQuery` only — never live provider in list/get |
| Indexes | Fingerprint, provider+external, sync key, year/famous, players, event, `game_date`, analysis fingerprint, job status, puzzle provider+external |
| Bounded sync concurrency | `provider_sync` fetches serially; HTTP caps `HTTP_PROVIDER_LICHESS/CHESSCOM_CONCURRENCY` |
| Streaming imports | `iter_pgn_games` / puzzle CSV row stream — no multi-GB `read_text` |
| Stockfish off HTTP | `POST …/analyze` enqueues Celery; engine runs in worker |

Contract: `performance.py`. Additive indexes: Alembic `h6b7c8d9e0f1`.

---

## Do not overengineer v1 (§36)

Stay in the **modular monolith**. Do **not** add Kafka, Elasticsearch, a
separate chess microservice, or a data lake just to ship hybrid chess.

Prefer until scale forces a change:

```text
PostgreSQL
existing Celery
existing object/file storage
existing provider clients
existing repositories
existing API
existing frontend
```

Contract: `scope_v1.py`. Operational catalog still ≠ warehouse (§18).

---

## Target architecture (§37)

Conceptual hybrid layout (prompt diagram) maps onto the **existing** modular
monolith — do **not** invent folders only to match ASCII art.

```text
backend/modules/chess_intelligence/
│  models/service/repository …… canonical game/puzzle domain
│  providers/ ………………… Lichess masters + puzzles + Chess.com
│  importers/ ………………… historical PGN (+ puzzle CSV)
│  fingerprint.py + dedupe.py … identity / multi-source
│  provider_sync_state.py ……… durable sync checkpoints
│  famous_* …………………… editorial curation
│  analysis_*.py + engine/ …… versioned Stockfish (no analysis/ dir)
│  engine/critical_moments.py … critical moments
│  content_opportunity*.py …… opportunity scoring
│  catalog_job_* ……………… async catalog jobs
│  local_first.py + router …… local-first API
          │
          ↓
frontend/src/api/chessData.ts
          │
          ↓
frontend/src/features/chess/
          │
          ↓
canonical selected game
          │
          ↓
backend/modules/chess_video/
```

Owner map / anti-rename rules: `target_architecture.py`. Full file tree:
[`chess-backend-structure.md`](./chess-backend-structure.md).

---

## Priority order (§38)

Ship in order. Contract + owners: `priority_order.py`.

| Band | Focus | Exit criteria |
|------|-------|---------------|
| **P0** | Local-first correctness (sync state, daily, outage, idempotency) | Catalog reads never need live providers |
| **P1** | Historical hybrid lifecycle (bootstrap, manifest, famous, provenance, no redownload) | Bootstrap once; use forever without scheduled redownload |
| **P2** | Analysis reuse (fingerprint, concurrency, force, engine version) | Identical analysis ≠ duplicate Stockfish |
| **P3** | Recent discovery → opportunity (schedule, eligibility, moments, score) | Recent/notable ≠ famous |
| **P4** | UX + ops (freshness UI, admin sync, runbook, metrics, FE tests, docs) | Hybrid operable without browser provider clients |

P0–P4 owners point at existing modules/tests (already landed in this hybrid pass).

---

## Critical acceptance criteria (§39)

Not complete unless all hold. Contract + evidence map: `acceptance_criteria.py`.

| ID | Criterion |
|----|-----------|
| AC01 | Local DB is operational source of truth |
| AC02 | Historical games are not routinely re-downloaded |
| AC03 | Recent games use incremental provider synchronization |
| AC04 | Sync position survives process restarts |
| AC05 | Failed syncs do not corrupt the checkpoint |
| AC06 | Same game from multiple sources → one canonical game |
| AC07 | All sources remain attributable |
| AC08 | Famous = curation, not another PGN copy |
| AC09 | Recent/notable ≠ famous |
| AC10 | Content opportunity ≠ famous/recent |
| AC11 | Normal GETs do not require provider availability |
| AC12 | Daily puzzle locally persisted before serve |
| AC13 | Provider outage → sensible stale fallback |
| AC14 | Equivalent Stockfish analysis reused |
| AC15 | Engine/config change → new analysis |
| AC16 | Concurrent identical analysis cannot duplicate work |
| AC17 | Existing chess-video renderer stays downstream |
| AC18 | Manual PGN/SAN/UCI video creation still works |
| AC19 | Frontend never contains provider credentials |
| AC20 | No unnecessary new scheduler/task system |
| AC21 | No duplicate canonical chess subsystem |

Guard: `test_chess_acceptance_criteria.py`.

---

## Supported chess providers

All remote I/O goes through `chess_intelligence.providers` (§15):

```text
ChessProvider family
├── HistoricalGameProvider  → lichess_masters, chesscom
└── PuzzleProvider          → lichess_puzzles
```

Resolve via `get_historical_game_provider` / `get_puzzle_provider` (registry).
Providers own protocol/auth/pagination/timeouts/rate limits/DTO parse only.
Canonical identity, dedupe, fame, content opportunity, and video stay in domain.

### Fingerprint + dedupe (§17)

Sole game identity layer — not provider IDs:

```text
sha256(starting_fen | uci_moves | result)
  → ChessGameDedupeService.upsert_game
  → ChessGame + ChessGameSource
```

Stable across comments, formatting, header order, and annotations. All ingress
(archive, provider sync, API import) converges here; providers never dedupe locally.

| Provider | Role | Auth | Notes |
|----------|------|------|-------|
| `lichess_masters` | Live masters explorer search + PGN | Optional `LICHESS_API_TOKEN` | Opening Explorer HTTP |
| `lichess_puzzles` | Daily / by-id puzzle API + CSV dump import | Optional token for site API | Bulk file from database.lichess.org |
| `chesscom` | PubAPI game retrieval | None (User-Agent required) | Fair-use rate limit |
| `pgn_archive` / `pgn_*` / `archive_*` | Bulk multi-game PGN files | N/A | Streaming importer; no scrapers |

Forbidden: unofficial HTML scrapers / SDK bypass of `core.http` (see dependency + source rules).
Frontend never calls Lichess/Chess.com directly.

---

## Configuration

Copy `backend/.env.example` → `backend/.env`. Chess-relevant keys (server-side only):

```env
LICHESS_API_TOKEN=
LICHESS_HTTP_TIMEOUT_SECONDS=20
CHESSCOM_HTTP_TIMEOUT_SECONDS=20
STOCKFISH_PATH=/usr/bin/stockfish
CHESS_ENGINE_DEPTH=12
CHESS_ENGINE_THREADS=1
CHESS_ENGINE_HASH_MB=64
```

Frontend may only set `VITE_API_BASE` — never provider tokens or Stockfish paths.
Full table: [`chess-configuration.md`](./chess-configuration.md).

---

## Historical game import

Postgres is an **operational catalog**, not a universal chess warehouse (§18).
Huge archives stay on disk/object storage; stream a selective subset into
`chess_games` (fingerprint dedupe + provenance):

```bash
cd backend
PYTHONPATH=.. .venv/bin/python -m backend.scripts.import_chess_pgn \
  --file /data/wch.pgn \
  --tenant-id 00000000-0000-4000-8000-000000000001 \
  --provider pgn_archive \
  --source-name world_championship \
  --batch-size 100 \
  --max-games 500 \
  --year-from 1950 \
  --year-to 2000 \
  --player Kasparov
```

Useful flags: `--dry-run`, `--skip-games N`, `--max-games N`, `--year-from` /
`--year-to`, `--player` / `--white` / `--black`, `--event`, `--min-rating`,
`--import-batch-id …`. Caps: `CHESS_PGN_IMPORT_MAX_GAMES_CAP`,
`CHESS_PROVIDER_SYNC_MAX_GAMES_CAP`. Content-opportunity / analysis remain
workflow selectors — not reasons to bulk-download every game.

Long-running catalog work can also be queued via `POST /api/v1/chess/jobs`.

---

## Puzzle import

Puzzles live on **`ChessPuzzle`**, separate from historical `ChessGame` storage (§19).
Bulk dumps can be huge — filter/cap into the operational puzzle catalog; do not
require millions of rows for v1. `source_game_*` is provenance only (never
auto-imports full games).

1. Download the Lichess puzzle dump externally (do not commit it).
2. Stream into `chess_puzzles`:

```bash
cd backend
PYTHONPATH=.. .venv/bin/python -m backend.scripts.import_lichess_puzzles \
  --file /data/lichess_db_puzzle.csv.zst \
  --tenant-id 00000000-0000-4000-8000-000000000001 \
  --limit 10000 \
  --min-rating 1200 --max-rating 2000 \
  --themes mate fork --min-popularity 50 \
  --openings Kings_Pawn \
  --batch-size 200
```

Configurable: rating, themes, popularity, openings, date range, source, `limit`
(+ `CHESS_PUZZLE_IMPORT_MAX_RECORDS_CAP`). Same importer/API scales later.

Live daily puzzle is **local-first** (hybrid §10):

```text
POST /puzzles/daily/refresh  OR  catalog job daily_puzzle_sync
        ↓
  Lichess provider → normalize → upsert ChessPuzzle
        ↓
GET /puzzles/daily  → local DB only (today, else stale + is_stale/freshness)
```

Provider outage → last local daily still served (`freshness=stale`). Frontend never
calls Lichess directly.

### Catalog jobs + Celery beat (§11 / §26)

Reuse **only** `ChessCatalogJob` + `run_chess_catalog_job_task` (no second scheduler).

| Operation | Kind / task | Cadence |
|-----------|-------------|---------|
| Historical bootstrap | `pgn_import` | Manual / deploy (never daily redownload) |
| Famous enrichment | `enrich_famous` | Manual after import/catalog update |
| Bulk puzzles | `puzzle_import` | Manual |
| Daily puzzle | `daily_puzzle_sync` | Beat once/day + bounded retries (default on) |
| Recent masters | `provider_sync` | Beat daily (default **off**); optional `EVERY_MINUTES` |
| Stockfish | `analyze_chess_game_task` | On demand / fingerprint reuse (never bulk daily) |

Config: `CHESS_SCHEDULE_DAILY_PUZZLE_*`, `CHESS_SCHEDULE_PROVIDER_SYNC_*`
(including optional `CHESS_SCHEDULE_PROVIDER_SYNC_EVERY_MINUTES` for tournament feeds).
Manual refresh: `POST /chess/jobs` or admin sync panel / daily refresh.

**Forbidden on beat:** historical PGN redownload, bulk reanalysis of all games
(`catalog_schedule.FORBIDDEN_AUTO_SCHEDULE_TOKENS`).

**§25 admin vs browse:** `GET /chess/games` never starts provider sync. Privileged
UI (`CatalogAdminSyncPanel`) enqueues catalog jobs; reanalyze stays on game detail.

**§21 discovery → opportunity:** `provider_sync` never sets `is_famous`. Opt-in
`CHESS_DISCOVERY_AUTO_ANALYZE_*` / job `auto_analyze` may enqueue Stockfish for
eligible new games → moments/tactics/`ChessContentOpportunityScore`.

---

## Source provenance

Every imported/discovered game retains provenance via `ChessGameSource` (§16).

Capture as available: provider, external ID, source URL, source name, `retrieved_at`,
license/provenance note, provider metadata.

```text
ChessGame
├── source: pgn_archive
├── source: lichess_masters
└── source: manual_curated_catalog
```

A later provider adds another source row — it does **not** overwrite earlier
`ChessGame.source_*` or collapse prior associations. Same provider+external ID
is idempotent (unique index + dedupe attach).

### Concurrency + idempotency (§28)

Safe to repeat: same archive, famous catalog, provider window, multi-provider
sighting, daily puzzle, analysis request, worker retry.

| Repeat | Outcome | Guarantee |
|--------|---------|-----------|
| Same game twice | one `ChessGame` | fingerprint unique + SAVEPOINT race |
| New provider, same game | + `ChessGameSource` | source unique + attach |
| Same source twice | no duplicate source | unique + IntegrityError → false |
| Same analysis profile | reuse job | `analysis_fingerprint` partial unique |
| Changed analysis profile | new job | different fingerprint |
| Sync failure / retry | HWM unchanged until clean | `ChessProviderSyncState` |

Contract: `idempotency.py`. Prefer DB uniques over SELECT-then-INSERT alone.

### Failure semantics (§29)

Provider / engine / archive failures stay isolated from catalog reads. Local
`ChessGame` / `ChessPuzzle` / `ChessGameSource` rows must not disappear because
a remote source is temporarily down.

| Failure | Local behavior |
|---------|----------------|
| Lichess unavailable | Browse/search use local DB only |
| Daily puzzle provider down | Last persisted daily (stale OK) |
| Provider sync fails | Previous `high_water_mark` kept |
| Stockfish unavailable | Catalog usable; analysis job `FAILED` |
| Malformed archive PGN | Error counted; import continues |

Contract: `failure_semantics.py`.

### Testing requirements (§30)

Hybrid scenarios live in the **existing** chess pytest modules. Guard map:
`backend/tests/test_chess_section30_coverage.py`. Phase 25 map remains
`test_chess_phase25_coverage.py`. Do not invent a parallel chess test tree.

```http
GET /api/v1/chess/games/{game_id}/provenance
GET /api/v1/chess/puzzles/{puzzle_id}/provenance
GET /api/v1/chess-videos/{job_id}/provenance
```

UI: provenance panel on game details. Catalog lookups by provider/external ID
resolve through primary denormalized fields **or** any linked `ChessGameSource`.

---

## Famous-game catalog

Curated YAML: `backend/modules/chess_intelligence/data/famous_games.yaml`.

Match titles onto imported games:

```bash
cd backend
PYTHONPATH=.. .venv/bin/python -m backend.scripts.apply_famous_catalog \
  --tenant-id 00000000-0000-4000-8000-000000000001 \
  --dry-run
```

Omit `--dry-run` to write `is_famous` / `famous_title` / tags. UI: Games → Famous.

---

## Stockfish setup

Stockfish is an **external binary**, not a PyPI package.

```bash
# Debian/Ubuntu example
sudo apt install stockfish
# then in backend/.env
STOCKFISH_PATH=/usr/games/stockfish
```

Empty `STOCKFISH_PATH` → analysis endpoints return 503. Engine knobs:
`CHESS_ENGINE_DEPTH`, `CHESS_ENGINE_TIME_LIMIT`, `CHESS_ENGINE_HASH_MB`,
`CHESS_ENGINE_THREADS`. Workers run analysis via Celery (`chess_analysis` tasks). Analysis identity is
`analysis_fingerprint` (game + engine + schema + settings) — matching COMPLETED /
QUEUED / RUNNING jobs are reused; FAILED is requeued; `force=true` supersedes
**same fingerprint only** (ply rows kept). Different depth/engine → new fingerprint →
history preserved (§14).

Select without recomputing:

| Profile | Behavior |
|---------|----------|
| `latest` | newest completed (else newest any) |
| `preferred` | deepest completed |
| `matching` | fingerprint or depth |

```http
GET /api/v1/chess/games/{id}/analysis?profile=preferred
GET /api/v1/chess/games/{id}/analysis?profile=matching&depth=18
GET /api/v1/chess/games/{id}/analyses
```

Concurrent analyze requests (§13): partial unique
`uq_chess_analysis_jobs_tenant_fingerprint_active` + SAVEPOINT insert +
`IntegrityError` reuse (same pattern as automation occurrence claim). FAILED
retries use atomic ``UPDATE … WHERE status='failed'`` so only one Celery dispatch wins.

---

## API routes

Base: `/api/v1` (auth + `content:write` for mutations).

### Catalog (`/chess`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/chess/games` | Search / filter historical games |
| GET | `/chess/games/famous` | Famous-tagged games |
| POST | `/chess/games/import` | Import one PGN payload |
| GET | `/chess/games/{id}` | Game detail |
| GET | `/chess/games/{id}/moves` | Annotated plies |
| GET | `/chess/games/{id}/provenance` | Provenance |
| POST | `/chess/games/{id}/video` | Create video from catalog game |
| POST | `/chess/games/{id}/analysis` | Enqueue Stockfish job |
| GET | `/chess/games/{id}/analysis` | Select analysis (`profile=latest\|preferred\|matching`) |
| GET | `/chess/games/{id}/analyses` | Multi-profile analysis history |
| GET | `/chess/games/{id}/content-score` | Content opportunity score |
| GET | `/chess/analysis/{job_id}` | Analysis job status |
| GET | `/chess/puzzles` | Puzzle search |
| GET | `/chess/puzzles/daily` | Daily puzzle (local; `is_stale` / `freshness` / `daily_utc`) |
| POST | `/chess/puzzles/daily/refresh` | Admin: sync daily from provider → local |
| GET | `/chess/puzzles/{id}` | Puzzle detail |
| GET | `/chess/puzzles/{id}/provenance` | Puzzle provenance |
| POST | `/chess/jobs` | Enqueue catalog job (202) |
| GET | `/chess/jobs/{id}` | Catalog job status |
| GET | `/chess/sync-states` | Inspect durable provider sync checkpoints (§33) |

### Video (`/chess-videos`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/chess-videos/validate` | Validate PGN/SAN/UCI |
| POST | `/chess-videos` | Create job (`source_text` or `chess_game_id`) |
| GET | `/chess-videos` | List jobs |
| GET | `/chess-videos/{id}` | Job detail |
| GET | `/chess-videos/{id}/provenance` | Video provenance |
| POST | `/chess-videos/{id}/retry` | Retry failed job |
| DELETE | `/chess-videos/{id}` | Delete job |

Interactive OpenAPI: `/api/v1/docs` when the API is running.

---

## Frontend workflow

Route: `/dashboard/chess-video`.

Tabs: **Games** | **Puzzles** | **Create** | **Preview** | **History**.

1. **Games** — search / famous / imported → View / Analyze / Create video (research-style cards).
2. **Puzzles** — browse + daily → `PuzzleViewer`.
3. **Create** — paste/upload PGN/SAN/UCI or handoff from catalog → validate → generate.
   Catalog handoff uses local `normalized_pgn` only (§22 — video never fetches providers).
4. **Preview / History** — poll render jobs, retry, delete.

API clients: `frontend/src/api/chessData.ts`, `chessVideos.ts`. Feature UI: `frontend/src/features/chess/`.

---

## Game → video workflow

```text
ChessGame (catalog) ──POST /chess/games/{id}/video──┐
                                                     ├→ ChessVideoJob → Celery video queue
Paste/upload PGN ───POST /chess-videos───────────────┘         → Pillow frames → FFmpeg → MinIO
```

Requirements: PostgreSQL, Redis, Celery worker listening on the **`video`** queue, `ffmpeg` on PATH (or `FFMPEG_BIN`), object storage configured. Details: [`chess-video.md`](./chess-video.md).

---

## Example developer commands

```bash
# Migrations (chess catalog + analysis tables)
cd backend && PYTHONPATH=.. .venv/bin/alembic upgrade head

# Unit tests (chess-focused)
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q \
  tests/test_chess_*.py tests/test_lichess_*.py tests/test_pgn_*.py \
  tests/test_famous_catalog.py tests/test_workflow_chess_intelligence_nodes.py

# Frontend chess UI tests
cd frontend && npm test -- --run src/features/chess src/pages/ChessVideoPage.test.tsx

# Repo checks
make check
make regression-unit

# Metrics snapshot after exercising imports/analysis
curl -s http://localhost:8000/api/v1/health/metrics | jq '.domain'
```

---

## Operational runbook (§33)

Reuse existing Python modules + `POST /chess/jobs` / analysis APIs. **No new
shell scripts.** Contract map: `operational_runbook.py`. Admin UI:
`CatalogAdminSyncPanel` (requires `content:write`).

| Operation | How |
|-----------|-----|
| Bootstrap historical archive | CLI `import_chess_pgn` **or** `POST /chess/jobs` `kind=pgn_import` |
| Historical famous enrichment | CLI `apply_famous_catalog` **or** `kind=enrich_famous` |
| Recent provider sync | `kind=provider_sync` (panel: “Run recent-game sync”) |
| Refresh daily puzzle | `POST /chess/puzzles/daily/refresh` **or** `kind=daily_puzzle_sync` |
| Inspect sync state | `GET /chess/sync-states` (HWM, last error, last job) |
| Retry failed sync | Re-enqueue same `provider_sync` params — HWM unchanged after failure |
| Reanalyze changed profile | `POST /chess/games/{id}/analyze` with new `depth` / settings (`force` optional) |

### Bootstrap archive

```bash
cd backend
PYTHONPATH=.. .venv/bin/python -m backend.scripts.import_chess_pgn \
  --file /data/wch.pgn \
  --tenant-id 00000000-0000-4000-8000-000000000001 \
  --provider pgn_archive \
  --source-name world_championship \
  --max-games 500
```

Or queue: `POST /api/v1/chess/jobs` with
`{"kind":"pgn_import","params":{"file_path":"/data/wch.pgn","provider":"pgn_archive","source_name":"world_championship","max_games":500}}`.

### Famous enrichment

```bash
cd backend
PYTHONPATH=.. .venv/bin/python -m backend.scripts.apply_famous_catalog \
  --tenant-id 00000000-0000-4000-8000-000000000001
```

Or `{"kind":"enrich_famous","params":{}}`.

### Recent sync + retry

```bash
# Enqueue (Bearer token with content:write)
curl -sS -X POST "$API/chess/jobs" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"kind":"provider_sync","params":{"provider":"lichess_masters","max_games":15}}'

# Inspect checkpoints
curl -sS "$API/chess/sync-states" -H "Authorization: Bearer $TOKEN"

# Poll job
curl -sS "$API/chess/jobs/$JOB_ID" -H "Authorization: Bearer $TOKEN"
```

If `result.sync_advanced` is false / `last_error_summary` set → re-POST the same
`provider_sync` job. Lookback overlap dedupes safely; watermark only advances on
clean runs.

### Daily puzzle refresh

```bash
curl -sS -X POST "$API/chess/puzzles/daily/refresh" -H "Authorization: Bearer $TOKEN"
# or
curl -sS -X POST "$API/chess/jobs" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"kind":"daily_puzzle_sync","params":{}}'
```

### Reanalyze with a new engine profile

```bash
curl -sS -X POST "$API/chess/games/$GAME_ID/analyze" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"depth":18}'
```

Same depth/engine/settings → reuse (`reused=true`). Different profile → new job.
`force: true` cancels/supersedes when needed.

---

## Related docs index

* [`chess-intelligence-phase1.md`](./chess-intelligence-phase1.md) — phased domain design log
* [`chess-configuration.md`](./chess-configuration.md) — env vars
* [`chess-observability.md`](./chess-observability.md) — logs / metrics
* [`chess-dependency-policy.md`](./chess-dependency-policy.md) — allowed deps
* [`chess-backend-structure.md`](./chess-backend-structure.md) — package layout
* [`chess-frontend-structure.md`](./chess-frontend-structure.md) — UI layout
* [`chess-ux-requirements.md`](./chess-ux-requirements.md) — UX patterns
* [`chess-video.md`](./chess-video.md) — render pipeline
* [`caching.md`](./caching.md) — provider cache TTLs
* [`observability/metrics.md`](./observability/metrics.md) — platform metrics ownership
