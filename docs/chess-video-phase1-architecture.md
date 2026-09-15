# Chess Video Generator — Phase 1 Architecture Note

Short analysis before implementing the low-resource chess match video pipeline.

## Files to reuse

| Area | Paths |
|------|--------|
| Auth / tenant | `backend/api/deps/auth.py` (`get_current_membership`, cookies+CSRF), `get_db` |
| API mount | `backend/api/router.py` (`/api/v1` include pattern) |
| Object storage | `backend/core/storage.py` (`ObjectStorage.upload_bytes`, `public_url_for`) |
| Config | `backend/core/config.py` (`FFMPEG_BIN`, `CELERY_QUEUE_VIDEO`, storage settings) |
| ORM base | `backend/db/base.py` (`UUIDPrimaryKeyMixin`, `TimestampMixin`, naming conventions) |
| FFmpeg ops | `backend/modules/video_pipeline/ffmpeg_render.py` (subprocess + `settings.FFMPEG_BIN`) — reuse patterns, not the storyboard/TTS media sequence model |
| Celery wiring | `backend/workers/tasks.py`, `task_defs/_common.py`, `celery_app.py`, `task_policy.py` |
| Frontend HTTP | `frontend/src/api/client.ts` (`apiFetch`, credentials, CSRF) |
| Query keys | `frontend/src/lib/queryKeys.ts` (`tenantQueryKey`) |
| UI primitives | `frontend/src/components/ui/{button,card,input,tabs,LoadingState,ErrorState,EmptyState}` |
| Shell / nav | `AppShell`, `routeManifest.ts`, `router.tsx` |
| Tenant scope | `useTenantScope`, `ErrorState` / `LoadingState` page patterns (e.g. Dashboard, Trending) |

## Files to extend

| Path | Change |
|------|--------|
| `backend/api/router.py` | Mount `chess_video` router at `/chess-videos` |
| `backend/db/model_registry.py` | Import chess_video models |
| `backend/workers/tasks.py` | Export `generate_chess_video_task` |
| `backend/workers/celery_app.py` | Route task → `video` queue |
| `backend/workers/task_policy.py` | Media workload policy (timeouts/retries/acks) |
| `Procfile.dev` | Already consumes `video` queue on worker — confirm stays listed |
| `frontend/src/app/router.tsx` | Route `/dashboard/chess-videos` |
| `frontend/src/navigation/routeManifest.ts` | Optional nav entry (prompt uses dashboard CTA; page route still required) |
| `frontend/src/pages/DashboardPage.tsx` | **Create Chess Video** action |
| `frontend/src/lib/queryKeys.ts` | Chess video tenant keys |
| `frontend/src/api/parityInventory.ts` | New endpoints |
| `backend/requirements.txt` (+ `pyproject.toml` if used for sync) | `chess`, `Pillow` |
| Alembic | New additive migration only |

## Files to create

```text
backend/modules/chess_video/
  __init__.py, models.py, schemas.py, parser.py, renderer.py,
  encoder.py, service.py, repository.py, router.py

backend/workers/task_defs/chess_video.py
backend/alembic/versions/<rev>_add_chess_video_jobs.py
backend/tests/… (parser, service, router isolation)

frontend/src/api/chessVideos.ts
frontend/src/pages/ChessVideoPage.tsx
(+ small feature components as needed under features/chess-video/)
```

## Existing patterns to follow

* **API**: FastAPI `APIRouter`, `response_model`, `Depends(get_db)` + `Depends(get_current_membership)`; tenant from `membership.tenant_id`; optional `require_permission` only when RBAC already used for similar media ops.
* **Transactions**: repositories `flush()`; services orchestrate; request/worker entrypoint `commit()`.
* **Models**: UUID PK + timestamps; `tenant_id` indexed; status enums as strings; JSON columns for settings/metadata.
* **Services**: domain module owns business logic; do **not** hang chess jobs off `ContentJob` / `content_plan_id`.
* **Celery**: sync task wrapper → `run_async_task` / `run_detached_async_task`; register in `tasks.py` + `task_routes` + `TASK_POLICIES`; media → **`video`** queue (same class as image/TTS assets).
* **Storage**: upload via `ObjectStorage`; keys tenant-scoped; store public URL + object key on job row.
* **Alembic**: additive migrations only; never rewrite history; follow `a1b2c3…` style with explicit `upgrade`/`downgrade`.
* **Frontend**: typed `api/*.ts` clients via `apiFetch`; TanStack Query with `tenantQueryKey`; lazy route; `LoadingState` / `ErrorState` / empty states; deep-link friendly where practical.
* **FFmpeg**: already in `backend/Dockerfile` (`apt install ffmpeg`) and host (`FFMPEG_BIN=ffmpeg`).

## Potential architecture conflicts

1. **`ContentJob` coupling** — Requires `content_plan_id` and editorial stages. Chess is a standalone deterministic render → **own `ChessVideoJob` (or equivalent) table**.
2. **`video_pipeline.FFmpegRenderService`** — Built for multi-segment storyboard + branding overlays. Chess needs frame PNGs → **one** encode. Reuse FFmpeg invocation style, not the full render service API.
3. **Approval/publishing** — Out of scope for this feature (preview only). Do not wire Telegram approval or publish jobs yet.
4. **Worker pool** — Procfile uses gevent workers for all queues including `video`. CPU-heavy Pillow/FFmpeg may need care (subprocess already isolates FFmpeg; keep frame generation streaming/temp-dir, not all frames in RAM).
5. **Permissions** — Many routes use membership only. Prefer same for chess create/list unless a dedicated permission already exists; avoid inventing unused RBAC codes.
6. **WebSocket `/ws/job/{job_id}`** — Exists for content jobs. Prefer React Query polling for chess status first (simpler, matches “low resource”); optional later reuse if job IDs share a convention.

## Phase 1 decision summary

Implement `backend/modules/chess_video` as a modular-monolith domain with Celery on the existing **`video`** queue, MinIO/S3 via `ObjectStorage`, and a dedicated React page + dashboard CTA — without extending `ContentJob`.
