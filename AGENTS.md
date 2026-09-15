# AGENTS.md

## Project

**SignalForge** is an AI-assisted content operations platform.

Core stack:

* Backend: Python 3.12, FastAPI, SQLAlchemy 2, Alembic
* Database: PostgreSQL
* Cache/queues: Redis + Celery
* Frontend: React 19, TypeScript, Vite
* UI: Tailwind, Radix UI
* Data fetching: TanStack Query
* Storage: MinIO/S3
* AI: local and OpenAI-compatible providers

Architecture is a **modular monolith with queue-driven background workflows**.

Preserve the approval-first publishing model. AI may ingest, analyze, draft, and prepare content; publishing must respect the existing approval and authorization workflow.

---

## Repository Structure

```text
backend/
  api/          FastAPI routes/dependencies
  core/         config, cache, HTTP, telemetry
  db/           sessions and DB infrastructure
  modules/      domain modules
  workers/      Celery workers/tasks
  alembic/      migrations
  prompts/      AI prompt templates
  tests/

frontend/
  src/api/      API clients
  src/app/      application setup/router
  src/components/
  src/features/
  src/hooks/
  src/pages/

docs/
infra/
```

Keep domain logic inside its domain module. Avoid generic dumping grounds such as large `utils.py` files.

---

## Engineering Priorities

When changing code, optimize in this order:

1. correctness
2. data integrity
3. security
4. reliability/idempotency
5. performance
6. maintainability
7. UI polish

Do not sacrifice correctness for shorter code.

---

## Backend Rules

Use async I/O for database, HTTP, Redis, and other I/O-bound operations.

Prefer:

```text
router -> service -> repository
```

Responsibilities:

* router: HTTP/auth/validation
* service: business logic/orchestration
* repository: SQL/database access

### Transactions

Request-scoped transaction ownership is the default.

* repositories mutate + `flush()`
* services compose operations
* request/worker entrypoint commits
* rollback on failure

Do not add arbitrary `commit()` calls inside repositories/services.

Explicit split-phase commits are allowed only for workflows requiring durable state before external I/O, such as publishing claims.

Never share one SQLAlchemy `AsyncSession` between concurrent asyncio tasks.

### Database

Prefer PostgreSQL operations over Python loops.

Use:

* bulk INSERT/UPDATE
* `RETURNING`
* `ON CONFLICT`
* set-based queries
* joins/window functions
* keyset pagination for large collections

Avoid:

* N+1 queries
* row-by-row persistence
* loading all rows then filtering/slicing in Python
* keeping transactions open during slow external API/LLM/media calls

Add indexes only after inspecting the query and preferably `EXPLAIN (ANALYZE, BUFFERS)`.

Never rewrite historical Alembic migrations. Create additive migrations.

---

## Concurrency & Performance

Use:

* `asyncio` for concurrent I/O
* bounded concurrency for external providers
* Celery for long-running/background work
* worker processes for CPU-heavy media operations

Do not use unbounded `asyncio.gather()`.

Do not use threads for async DB/HTTP operations.

Use `asyncio.to_thread()` only for measured blocking synchronous libraries.

Never increase worker concurrency without considering:

* PostgreSQL pool size
* Redis capacity
* external API rate limits
* memory/CPU usage

Cache expensive stable operations where appropriate, but preserve tenant isolation and explicit invalidation.

---

## External Services

Use centralized HTTP/provider infrastructure when available.

Preserve:

* connection pooling
* timeouts
* bounded concurrency
* retries/backoff
* `Retry-After`
* idempotency
* observability

Do not duplicate provider-specific retry logic unnecessarily.

Never log API keys, tokens, passwords, authorization headers, or other secrets.

---

## Celery Tasks

Tasks must be:

* idempotent where possible
* retry-safe
* observable
* small enough to recover independently

Persist durable state before/after important external operations.

Long workflows should use explicit stages rather than one monolithic task.

---

## Frontend Rules

Use existing stack and primitives before adding dependencies.

Prefer:

* TanStack Query for server state
* typed domain API clients
* React Hook Form + Zod for forms
* Radix primitives for tabs/dialogs/tooltips
* existing shared components/hooks

Keep API query keys centralized and stable.

Invalidate/refetch only affected data after mutations.

Do not fetch data for inactive sections unless needed.

For long pages:

* use meaningful tabs
* lazy-render expensive inactive sections
* use tooltips/help disclosures for secondary explanations
* keep critical errors/warnings visible

Tabs should be URL/deep-link friendly when practical.

User-facing backend capabilities should have a frontend counterpart unless intentionally classified as webhook, worker/internal, observability, or machine-only functionality.

---

## React Performance

Avoid repeated linear searches during rendering.

Convert repeatedly searched collections to maps/sets when useful.

Do not add `useMemo`/`memo` everywhere. Profile or use them where derived work or reference stability matters.

For large datasets:

1. server-side pagination
2. efficient rendering
3. virtualization only if still necessary

Preserve route-level code splitting.

---

## File Size & Design

Normal production files should generally stay below **300 lines**.

When a file grows too large, split it by responsibility.

Do not satisfy the line limit by:

* compressing code
* creating meaningless wrapper files
* moving unrelated functions into generic utility modules

Aim for:

* small cohesive functions
* clear domain boundaries
* explicit types
* low cyclomatic complexity

Concise code means lower cognitive complexity, not fewer characters.

Exempt generated files, lockfiles, and historical migrations from normal line-count rules.

---

## Dormant Modules

Modules under:

```text
backend/modules/_dormant/
```

are intentionally quarantined.

Do not:

* mount their routers
* register their models
* create migrations for them
* delete/reactivate them casually

Follow `docs/dormant-modules.md` and existing contract tests.

---

## Dead Code

Delete code only when evidence shows it is unused.

Check:

* imports
* route registration
* worker registration
* dynamic loading
* tests
* compatibility contracts

Do not delete empty `__init__.py` files merely because they are empty.

Do not remove compatibility facades protected by tests without updating the architecture intentionally.

---

## Testing

After backend changes, run relevant tests plus:

```bash
make check
```

For broader changes:

```bash
make quality-gates
```

Useful commands:

```bash
make fix
make check
make regression
make quality-gates
```

Backend:

```bash
cd backend
.venv/bin/ruff check .
.venv/bin/mypy .
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q
```

Frontend:

```bash
cd frontend
npm run lint
npx tsc --noEmit
npm test -- --run
npm run build
```

Run Playwright for affected end-to-end workflows.

Every bug fix should add or update a regression test when practical.

---

## Before Finishing

Verify:

* tests/build pass
* no new N+1 queries
* no unnecessary DB commits
* no long transaction around external I/O
* no unbounded concurrency
* tenant isolation remains intact
* permissions/auth remain intact
* background operations remain idempotent
* frontend loading/error/empty states work
* no secrets enter logs or source
* new user-facing backend functionality is represented in the UI
* documentation reflects important architectural changes

For performance work, measure before and after. Do not claim an optimization without evidence.

Prefer the smallest change that solves the root cause without weakening existing architecture or tests.
