# Chess Video Generator

Low-resource pipeline that turns PGN / SAN / UCI games into 2D MP4 match videos.

## Scope

* Deterministic Pillow board frames (no browser renderer, Playwright, Stockfish, LLM, or TTS)
* One PNG per board position; FFmpeg timing holds each frame
* Single-pass H.264 encode (`libx264`, `yuv420p`, `faststart`)
* Direct MinIO/S3 upload via `ObjectStorage.upload_file` (no `read_bytes()` on MP4)
* Tenant-scoped jobs with SHA-256 render fingerprint cache reuse
* Celery task `generate_chess_video_task` on the **`video`** queue

Related: Phase 1 architecture note — [`docs/chess-video-phase1-architecture.md`](./chess-video-phase1-architecture.md). UI entry is sidebar **ChessMaster** → `/dashboard/chess-video` (not an Overview card).

## Architecture

```text
PGN/SAN/UCI  (paste)     OR     ChessGame.normalized_pgn (catalog id)
                \                     /
                 ↓                   ↓
              python-chess (parser)
                 ↓
              Normalized Game
                 ↓
              Pillow Frames (one position at a time)
                 ↓
              FFmpeg (single encode)
                 ↓
              MP4 + thumbnail.png
                 ↓
              S3/MinIO (upload_file)
```

§22 — `chess_video/` is **downstream only**. It must not call Lichess/Chess.com,
download PGNs, or run dedupe/ingestion. Catalog selection uses
`chess_game_id` → local DB PGN. Manual PGN/SAN/UCI remains supported.

## Supported move formats

| Format | Example | Notes |
|--------|---------|--------|
| **PGN** | Headers + `1. e4 c5 2. Nf3 …` | Mainline only; variations ignored. Supports `FEN` / `SetUp` |
| **SAN** | `1. e4 e5 2. Nf3 Nc6` | Move numbers / results normalized |
| **UCI** | `e2e4 e7e5 g1f3` | Each token verified against `board.legal_moves` |
| **auto** | (detect) | PGN headers → PGN; all-UCI tokens → UCI; else SAN |

Limits: **2 MB** input, **1000** plies. Illegal moves return ply + FEN context.

## Dependencies

| Dependency | Role |
|------------|------|
| `chess` (`python-chess`) | Authoritative rules / PGN / SAN / UCI |
| `Pillow` | 2D board PNG frames |
| Host **`ffmpeg`** (`FFMPEG_BIN`, default `ffmpeg`) | Single-pass H.264 encode |
| Object storage (MinIO/S3 via `ObjectStorage`) | MP4 + thumbnail upload |
| PostgreSQL | `chess_video_jobs` persistence |
| Redis + Celery | Background render on `video` queue |

Python packages are in `backend/requirements.txt` / `backend/pyproject.toml`. Piece PNGs are committed under `backend/modules/chess_video/assets/pieces/` (see `ATTRIBUTION.md`).

## Celery / queue

* Task: `backend.workers.tasks.generate_chess_video_task`
* Queue: **`video`** (`settings.CELERY_QUEUE_VIDEO`)
* Policy: `workload=media`, `acks_late=True`, `max_retries=1`, soft 480s / hard 600s
* Specialized media concurrency default: `CELERY_WORKER_MEDIA_CONCURRENCY=1`

API create/retry only enqueue after DB commit; FastAPI never blocks on Pillow/FFmpeg.

## Object storage requirement

Completed jobs upload:

* `tenants/{tenant_id}/chess-videos/{job_id}/video.mp4`
* `tenants/{tenant_id}/chess-videos/{job_id}/thumbnail.png`

Requires `STORAGE_BUCKET` (and related MinIO/S3 settings) configured. Upload uses `upload_file` so the MP4 is not loaded entirely into Python memory.

## FFmpeg requirement

* Binary on `PATH` or set `FFMPEG_BIN`
* Encode flags: concat demuxer → `libx264`, `yuv420p`, `+faststart`, `-an`
* Present in `backend/Dockerfile` via `apt install ffmpeg`

## Module layout

```text
backend/modules/chess_video/
  parser.py        PGN/SAN/UCI → ParsedChessGame
  renderer.py      ChessVideoRenderer (Pillow)
  frames.py        streaming frame_NNNN.png writer
  encoder.py       concat demuxer + one FFmpeg process
  pipeline.py      tempdir orchestration + cleanup
  fingerprint.py   render cache key
  service.py       validate/create/process/retry
  router.py        /api/v1/chess-videos
  assets/pieces/   local PNG piece set (+ ATTRIBUTION.md)

backend/workers/task_defs/chess_video.py
frontend/src/api/chessVideos.ts
frontend/src/pages/ChessVideoPage.tsx
```

Dashboard CTA → `/dashboard/chess-video` via sidebar **ChessMaster**.

## API

Auth: cookie session + `content:write`.

| Method | Path | Notes |
|--------|------|--------|
| POST | `/api/v1/chess-videos/validate` | Parse only |
| POST | `/api/v1/chess-videos` | Queue job (or fingerprint cache hit) |
| GET | `/api/v1/chess-videos` | Tenant history |
| GET | `/api/v1/chess-videos/{job_id}` | Status / result |
| POST | `/api/v1/chess-videos/{job_id}/retry` | Failed/cancelled only |

## Render presets

| Preset | Size | FPS | Encoder |
|--------|------|-----|---------|
| `economy_vertical` (default) | 720×1280 | 24 | ultrafast / CRF 26 |
| `social_vertical` | 1080×1920 | 30 | veryfast / CRF 23 |
| `square` | 1080×1080 | 30 | veryfast / CRF 23 |
| `horizontal` | 1920×1080 | 30 | veryfast / CRF 23 |

## Resource profile

* Peak RAM ≈ one board frame + FFmpeg process (not N frames × N encodes)
* Media worker soft/hard limits: 480s / 600s, `acks_late`, max 1 retry
* Prefer video-queue concurrency **1–2** on small hosts; do not lower unrelated queues
* Bottlenecks: Pillow draw cost × ply count; FFmpeg encode; object storage upload bandwidth

### Phase 21 audit (verified)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| No browser renderer / Playwright | Pass | Pillow `ChessVideoRenderer` only |
| No Stockfish / LLM / TTS / AI | Pass | `python-chess` + Pillow + FFmpeg only |
| No full MP4 in Python RAM | Pass | `ObjectStorage.upload_file` → boto3 file upload |
| No all-frames-in-RAM | Pass | `frames.py` save+`close()` per position; only path list retained |
| No one-MP4-per-move | Pass | Single `encode_frames_to_mp4` / one `subprocess.run` |
| No runtime asset download | Pass | Local `assets/pieces/*.png` |
| One position image at a time | Pass | Sequential render loop |
| One main FFmpeg encode | Pass | Concat demuxer → one libx264 pass |
| Direct file upload | Pass | Disk MP4/thumbnail → S3/MinIO |
| Temp cleanup | Pass | `cleanup_pipeline` / `shutil.rmtree` in `finally` |
| Render cache | Pass | SHA-256 fingerprint + tenant completed-job reuse |
| Isolated media worker queue | Pass | Task routed to `CELERY_QUEUE_VIDEO`, policy `workload=media` |

### Approximate cost model

| Stage | Scales with | Notes |
|-------|-------------|--------|
| Parse | O(plies) | Negligible vs render |
| Pillow frames | plies × resolution | Dominant CPU before encode; disk writes `frame_NNNN.png` |
| FFmpeg | resolution × total duration × fps | One process; economy preset uses `ultrafast` / CRF 26 |
| Upload | file size | Streamed; not loaded into app memory |
| Cache hit | O(1) DB lookup | Skips Pillow + FFmpeg entirely |

Rough local envelope for a ~40-ply game at `economy_vertical` (720×1280, ~1s/move): tens of MB peak Python RSS beyond FFmpeg, seconds–tens of seconds wall time depending on host CPU.

### Remaining bottlenecks / ops notes

1. **Shared Procfile worker** — `Procfile.dev` runs one gevent worker (`--concurrency=4`) across many queues including `video`. CPU-heavy Pillow/FFmpeg under gevent can stall other tasks. Prefer a dedicated media worker: `CELERY_WORKER_MEDIA_CONCURRENCY=1` (or 2) with `--queues=video` only on constrained hosts.
2. **Disk temp space** — All PNGs exist until encode finishes; long games × large presets need free disk under the temp dir.
3. **Gevent + blocking encode** — Encode runs via `asyncio.to_thread` in the async task path; keep media concurrency low so multiple FFmpeg/Pillow jobs do not contend.
4. **Fingerprint cache** — Reuses storage URLs; deleting underlying objects without invalidating jobs can yield dead links (ops concern, not MVP).

## Local development

1. Ensure PostgreSQL, Redis, MinIO, and FFmpeg are available (same as main stack).
2. Apply migrations (`cd backend && alembic upgrade head`) — includes `chess_video_jobs`.
3. Start API + worker consuming the `video` queue (`Procfile.dev` / Honcho).
4. Confirm storage env (`STORAGE_BUCKET`, endpoint, keys) so uploads succeed.
5. Open **ChessMaster** in the left sidebar → `/dashboard/chess-video`.

## Testing

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q \
  tests/test_chess_video_*.py tests/test_object_storage_upload_file.py

cd frontend
npm test -- --run src/pages/ChessVideoPage.test.tsx
npx tsc --noEmit
```
