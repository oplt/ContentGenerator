# AGENTS.md

## Project

**SignalForge** is an AI-assisted content operations platform.

Main stack:

* Backend: FastAPI, SQLAlchemy, PostgreSQL, Redis, Celery
* Frontend: React 19, TypeScript, Vite, Tailwind
* AI: Ollama and OpenAI-compatible providers
* Infrastructure: Docker Compose, MinIO/S3

The architecture is a modular monolith with asynchronous worker queues.

## Repository Structure

```text
backend/
  api/        FastAPI routes
  core/       config, logging, storage, telemetry
  db/         database models and sessions
  modules/    domain logic
  workers/    Celery tasks
  prompts/    AI prompt templates

frontend/
  src/api/         API clients
  src/components/  shared components
  src/features/    feature modules
  src/pages/       application pages

infra/             infrastructure files
docs/              documentation
```

## Development Rules

* Prefer small, focused changes.
* Follow existing architecture and naming conventions.
* Keep domain logic out of API route handlers.
* Keep frontend API access inside `src/api/`.
* Reuse existing components before creating new ones.
* Never commit secrets, `.env` files, credentials, or generated runtime artifacts.
* Preserve the **approval-first** publishing model.
* Do not bypass approval or publishing safety checks.
* Keep publishing in dry-run mode unless explicitly changing production behavior.

## Validation

Before finishing a change, run:

```bash
make check
make regression-unit
```

For larger changes:

```bash
make quality-gates
```

Frontend-specific checks:

```bash
cd frontend
npm test -- --run
npm run build
```

Backend tests:

```bash
cd backend
pytest
```

## Database Changes

Use Alembic for schema changes.

Do not modify the database schema without adding or updating the corresponding migration.

## AI / Provider Changes

Provider-specific behavior should stay behind adapters.

Avoid coupling domain logic directly to Ollama, OpenAI, or another provider.

Prompts should remain centralized in the existing prompt infrastructure when practical.

## GitNexus

When GitNexus is available:

1. Check symbol impact before significant edits.
2. Inspect callers/callees before refactoring shared code.
3. Run change detection before committing.

Avoid blind global renames or large refactors without checking their dependency impact.

## Definition of Done

A change is complete when:

* implementation matches existing architecture
* relevant tests pass
* lint/type checks pass
* no secrets or generated artifacts are committed
* documentation/configuration is updated when behavior changes
* approval and publishing safeguards remain intact
