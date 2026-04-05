# Generic App

Generic full-stack starter with:

- FastAPI backend
- React + Vite frontend
- PostgreSQL, Redis, and MinIO for local infrastructure
- Celery workers for asynchronous jobs, using Redis as broker/result backend
- JWT auth with refresh rotation
- Admin settings, notifications, profile, and project modules
- Optional platform modules for billing, API keys, webhooks, feature flags, and email templates
- Sentry/OpenTelemetry hooks and S3-compatible avatar storage

## Local Setup

1. Start infrastructure:

```bash
docker compose -f infra/docker-compose.yml up -d
```

2. Configure the backend:

```bash
cd backend
cp .env.example .env
uv sync
.venv/bin/alembic upgrade head
```

3. Start the backend:

```bash
cd backend
.venv/bin/uvicorn backend.api.main:app --reload
```

4. Start the Celery worker:

```bash
cd backend
.venv/bin/celery -A backend.workers.celery_app:celery_app worker --loglevel=INFO --queues=default,email
```

5. Configure the frontend:

```bash
cd frontend
cp .env.example .env
npm install
```

6. Start the frontend:

```bash
cd frontend
npm run dev
```

## Notes

- Local object storage uses MinIO on `http://localhost:9000` and its console on `http://localhost:9001`.
- Redis now serves both app-level caching/token storage and the Celery broker/result backend.
- The first Celery-backed workflow is outbound email delivery for verification and password reset flows.
- Set `CELERY_TASK_ALWAYS_EAGER=true` in `backend/.env` if you want queued email work to execute inline without a worker process.
- Avatar uploads are stored in the configured S3-compatible bucket instead of a placeholder path.
- `/admin/platform` lets you rename the app, rename the core domain labels, pick a module pack, and manage plans, flags, and email templates.
- Set `ADMIN_SIGNUP_INVITE_CODE` in `backend/.env` to allow invite-only admin registration during sign-up.
- Module packs are intended for clone-time reuse:
  - `lean_saas`
  - `automation_suite`
  - `client_portal`
  - `full_platform`
- Observability is enabled through backend config:
  - `SENTRY_DSN`
  - `SENTRY_TRACES_SAMPLE_RATE`
  - `OTLP_ENDPOINT`
  - `OTLP_INSECURE`
