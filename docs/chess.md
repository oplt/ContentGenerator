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

---

## Supported chess providers

| Provider | Role | Auth | Notes |
|----------|------|------|-------|
| `lichess_masters` | Live masters explorer search + PGN | Optional `LICHESS_API_TOKEN` | Opening Explorer HTTP |
| `lichess_puzzles` | Daily / by-id puzzle API + CSV dump import | Optional token for site API | Bulk file from database.lichess.org |
| `chesscom` | PubAPI game retrieval | None (User-Agent required) | Fair-use rate limit |
| `pgn_archive` / `pgn_*` / `archive_*` | Bulk multi-game PGN files | N/A | Streaming importer; no scrapers |

Forbidden: unofficial HTML scrapers / SDK bypass of `core.http` (see dependency + source rules).

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

Stream a multi-game `.pgn` into `chess_games` (fingerprint dedupe, provenance metadata):

```bash
cd backend
PYTHONPATH=.. .venv/bin/python -m backend.scripts.import_chess_pgn \
  --file /data/wch.pgn \
  --tenant-id 00000000-0000-4000-8000-000000000001 \
  --provider pgn_archive \
  --source-name world_championship \
  --batch-size 100
```

Useful flags: `--dry-run`, `--skip-games N`, `--max-games N`, `--import-batch-id …`.

Long-running catalog work can also be queued via `POST /api/v1/chess/jobs`.

---

## Puzzle import

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
  --batch-size 200
```

Live daily / by-id puzzles: `GET /api/v1/chess/puzzles/daily` and search API (provider HTTP + cache).

---

## Source provenance

Each catalog entity keeps provider, external id, URL, license note, import batch, fingerprints.

```http
GET /api/v1/chess/games/{game_id}/provenance
GET /api/v1/chess/puzzles/{puzzle_id}/provenance
GET /api/v1/chess-videos/{job_id}/provenance
```

UI: provenance panel on game details. Multi-source rows live on `ChessGameSource` when the same fingerprint is seen from multiple providers.

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
`CHESS_ENGINE_THREADS`. Workers run analysis via Celery (`chess_analysis` tasks).

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
| GET | `/chess/games/{id}/analysis` | Latest analysis |
| GET | `/chess/games/{id}/content-score` | Content opportunity score |
| GET | `/chess/analysis/{job_id}` | Analysis job status |
| GET | `/chess/puzzles` | Puzzle search |
| GET | `/chess/puzzles/daily` | Daily puzzle |
| GET | `/chess/puzzles/{id}` | Puzzle detail |
| GET | `/chess/puzzles/{id}/provenance` | Puzzle provenance |
| POST | `/chess/jobs` | Enqueue catalog job (202) |
| GET | `/chess/jobs/{id}` | Catalog job status |

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
3. **Create** — paste/upload PGN or handoff from catalog → validate → generate.
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
