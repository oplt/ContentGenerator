# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SignalForge** is a multi-tenant SaaS for AI-powered social media content operations. It implements a full pipeline: source ingestion → story clustering → content generation → approval (WhatsApp) → publishing (X, Instagram, TikTok, YouTube, Bluesky) → analytics.

## Common Commands

### Infrastructure
```bash
make infra-up          # Start PostgreSQL, Redis, MinIO via Docker Compose
make infra-down        # Stop infrastructure
```

### Backend
```bash
cd backend
uv run fastapi dev api/main.py   # Or: make backend-dev
uv run alembic upgrade head      # Apply migrations
uv run alembic revision --autogenerate -m "description"  # New migration
uv run pytest                    # All tests
uv run pytest tests/path/test_file.py::test_name  # Single test
uv run ruff check .              # Lint
uv run mypy .                    # Type check
```

### Frontend
```bash
cd frontend
npm run dev            # Vite dev server (port 5173) — or: make frontend-dev
npm run build          # Production build
npm run lint           # ESLint
npm test               # Vitest
npx playwright test    # E2E tests
```

### Celery Worker
```bash
make worker-dev        # Run all queues with auto-reload
```

### Seed Demo Data
```bash
make seed              # Creates demo@example.com / password1234
```

### Run Everything
```bash
docker compose up --build   # All services in containers
```

## Architecture

### High-Level Flow
```
React Frontend (port 5173)
    ↓ REST API
FastAPI Backend (port 8000)
    ↓ async SQLAlchemy
PostgreSQL 16  ←→  Redis 7 (cache + Celery broker)
    ↓
Celery Workers (multiple queues: ingestion, enrichment, generation, approvals, publish, analytics)
    ↓
External: WhatsApp, X/Twitter, Instagram, TikTok, YouTube, Bluesky, MinIO (S3)
```

### Backend Module Structure

Each domain module under `backend/modules/` follows this pattern:
```
module_name/
  ├── models.py      # SQLAlchemy ORM models
  ├── schemas.py     # Pydantic request/response schemas
  ├── service.py     # Business logic
  ├── repository.py  # Data access (SQL queries)
  └── router.py      # FastAPI route handlers
```

Key modules and their responsibilities:
- **identity_access** — JWT auth, users, roles, permissions
- **platform** — Multi-tenant setup, workspace management
- **source_ingestion** — RSS/Sitemap/Web parsing and article fetching
- **story_intelligence** — Story clustering, trend scoring
- **content_strategy** — Brand profiles, content plans, guardrails
- **content_generation** — LLM-based draft generation (text/video)
- **approvals** — WhatsApp approval workflow
- **publishing** — Social platform scheduling and publishing
- **analytics** — Metrics sync and dashboard data
- **calendar** — Content calendar entries
- **audit** — Audit logs

### Core Infrastructure (`backend/core/`)
- `config.py` — Pydantic Settings; all config comes from environment
- `security.py` — JWT, Argon2 hashing, crypto
- `storage.py` — S3/MinIO file operations
- `cache.py` — Redis client
- `rate_limit.py` — Rate limiting
- `telemetry.py` — OpenTelemetry + Sentry
- `logging.py` — structlog setup
- `error_handler.py` — Global exception → HTTP response mapping

### Database Conventions
- All models use mixins from `db/base.py`: `UUIDPrimaryKeyMixin`, `TimestampMixin`, `SoftDeleteMixin`, `VersionMixin`
- UUID primary keys everywhere
- Soft deletes via `deleted_at` timestamp
- Optimistic locking via `version` column
- Migrations managed by Alembic in `backend/alembic/versions/`

### Worker Queues (Celery)
Defined in `workers/celery_app.py`. Task entry points in `workers/tasks.py`:
- `poll_sources_task` — Scheduled RSS polling
- `ingest_source_task` — Fetch and parse articles
- `generate_content_task` — LLM content generation
- `send_approval_task` — WhatsApp approval dispatch
- `publish_due_jobs_task` — Publish scheduled posts
- `sync_analytics_task` — Pull social platform metrics

### Frontend Structure
- **State:** Zustand (`stores/`) for auth; TanStack Query for server state
- **API layer:** `src/api/` — typed Axios wrappers per domain
- **Forms:** React Hook Form + Zod schemas
- **UI components:** `src/components/ui/` (shadcn-style primitives)
- **Routing:** React Router v7 with route guards

## Key Environment Variables

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/content_generator
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=change-me

# Storage (MinIO local)
STORAGE_ENDPOINT_URL=http://localhost:9000
STORAGE_ACCESS_KEY=minioadmin
STORAGE_SECRET_KEY=minioadmin
STORAGE_BUCKET=content-generator

# LLM (use "mock" for local dev)
LLM_PROVIDER=mock
LLM_MODEL=mock-gpt
LLM_API_KEY=

# WhatsApp (use "stub" for local dev)
WHATSAPP_PROVIDER=stub
SOCIAL_DRY_RUN_BY_DEFAULT=true   # Prevents real social posts in dev
```

Copy `backend/.env.example` to `backend/.env` before first run.

## Multi-Tenancy

Every model is scoped to a `tenant_id`. The `platform` module manages tenant creation. All API routes extract the tenant from the authenticated user's JWT. Repository queries always filter by `tenant_id`.

## Adding a New Module

1. Create `backend/modules/<name>/` with `models.py`, `schemas.py`, `repository.py`, `service.py`, `router.py`
2. Import and include the router in `backend/api/router.py`
3. Add models to `backend/db/base.py` imports so Alembic detects them
4. Generate migration: `uv run alembic revision --autogenerate -m "add <name> tables"`

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **content_generator** (4497 symbols, 14991 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/content_generator/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/content_generator/context` | Codebase overview, check index freshness |
| `gitnexus://repo/content_generator/clusters` | All functional areas |
| `gitnexus://repo/content_generator/processes` | All execution flows |
| `gitnexus://repo/content_generator/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
