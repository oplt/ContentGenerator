# SignalForge

SignalForge is a modular-monolith SaaS for multi-tenant AI social content operations. It ingests live sources, clusters and scores stories, generates text and video drafts, routes approvals through WhatsApp, publishes to connected channels, and normalizes analytics back into the dashboard.

## Stack

- Backend: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Redis, Celery, Pydantic v2, OpenTelemetry, structlog
- Content pipeline: feedparser, trafilatura, Playwright-ready adapters, ffmpeg, faster-whisper-compatible interfaces
- Frontend: React, Vite, TypeScript, React Router, TanStack Query, Zustand, React Hook Form, Zod, Tailwind, shadcn-style components, Recharts
- Dev tooling: Docker Compose, MinIO, Makefile, pre-commit, GitHub Actions

## Local startup

1. Start infra:

```bash
make infra-up
```

2. Install backend dependencies and migrate:

```bash
cd backend
cp .env.example .env
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
```

3. Install frontend dependencies:

```bash
cd frontend
cp .env.example .env
npm install
```

4. Seed the demo tenant:

```bash
make seed
```

5. Run the app:

```bash
make backend-dev
make worker-dev
make frontend-dev
```

The seeded login is `demo@example.com` / `password1234`.

## Product flow

1. Add or edit sources in `/dashboard/sources`.
2. Trigger ingestion to create raw articles and story clusters.
3. Create a content plan from a cluster.
4. Generate drafts and open the content job detail.
5. Send the draft for approval.
6. In local mode, simulate WhatsApp approval with the stub webhook or approve from tests.
7. Publish via stub providers or manual fallback providers.
8. Sync analytics and inspect dashboard charts.

## Architecture notes

- The repo uses a modular monolith with internal bounded contexts and Celery-backed async seams.
- Local dev defaults to stub providers for WhatsApp and social publishing; real provider wiring is capability-gated.
- The initial migration uses SQLAlchemy metadata creation for speed. Future migrations can refine table-level DDL incrementally.

## Commands

- `make dev`
- `make lint`
- `make test`
- `make e2e`
- `make seed`
- `docker compose up --build`
