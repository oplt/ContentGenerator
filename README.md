# SignalForge

SignalForge is a production-minded autonomous AI content operations platform built as a modular FastAPI + React monolith. It ingests trend signals, normalizes and scores candidate topics, generates editorial briefs and platform-native assets, routes mandatory approvals through Telegram, publishes through adapter-based social integrations, and feeds performance data back into future ranking and generation decisions.

The current operating model is Telegram-first and semi-autonomous:

- the system continuously ingests, scores, and prepares work
- operators approve topic, brief, asset, and publish gates in Telegram
- dry-run publishing remains the default safe mode for local development

## Current architecture

- Backend: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Redis, Celery, Pydantic v2
- Frontend: React, Vite, TypeScript, Tailwind
- Object storage: MinIO/S3-compatible
- Inference: local-first adapter layer for Ollama, vLLM, llama.cpp, plus OpenAI-compatible endpoints
- Media pipeline: FFmpeg-ready video assembly with voice, captions, thumbnail, and preview outputs

## Core flow

1. Connect sources such as RSS, Reddit, sitemaps, blogs, official feeds, and optional best-effort trend/social connectors.
2. Ingest and normalize raw items into scored story clusters with explicit workflow state.
3. Generate and approve editorial briefs in Telegram.
4. Generate content assets and route them through asset approval in Telegram.
5. Publish through dry-run or real platform adapters.
6. Sync analytics and feed outcomes back into scoring and prompt decisions.

## Local run

1. Start the local stack:

```bash
docker compose up -d postgres redis minio ollama
```

2. Configure the backend:

```bash
cd backend
cp .env.example .env
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
```

3. Configure the frontend:

```bash
cd frontend
cp .env.example .env
npm install
```

4. Seed the demo workspace:

```bash
make seed
```

5. Run the services:

```bash
make backend-dev
make worker-dev
make frontend-dev
```

The seeded operator login is `demo@example.com` / `password1234`.

## Important env contracts

- `LLM_PROVIDER`: `ollama`, `vllm`, `llamacpp`, `openai_compatible`, or `mock`
- `LLM_TASK_MODELS_JSON`: per-task model overrides, for example `{"structured_json":"llama3.1:8b"}`
- `CSRF_SECRET`: required for cookie-authenticated refresh/logout protection
- `ENCRYPTION_KEY`: required in production for encrypted local credential storage
- `EXTERNAL_SECRET_REFERENCES_JSON`: optional JSON map for resolving external secret references at runtime
- `TELEGRAM_WEBHOOK_SECRET` and `TELEGRAM_CALLBACK_SIGNING_SECRET`: webhook and callback protection
- `SOCIAL_DRY_RUN_BY_DEFAULT=true`: recommended for local development
- `ENABLE_GOOGLE_TRENDS_CONNECTOR=false`: optional and intentionally best-effort

Production note:

- production bootstrap now fails fast if `JWT_SECRET`, `CSRF_SECRET`, `ENCRYPTION_KEY`, Telegram secrets, cookie security, or public HTTPS configuration are weak or missing

## Notable implementation decisions

- Trend workflow is explicit: `new -> queued_for_review -> brief_ready -> approved_topic -> asset_generation -> asset_review -> publish_ready -> published`
- Telegram callbacks are now signed to reduce spoofed approval risk
- High-risk content remains gated by deterministic scoring plus confirmation rules before content generation
- Local model routing is adapter-based so inference can move between Ollama, vLLM, llama.cpp, and OpenAI-compatible servers without rewriting the pipeline

See:

- `docs/editorial-workflow.md`
- `docs/implementation-report.md`
- `docs/local-models.md`
- `docs/examples/brand-configs.md`
- `docs/examples/telegram-cards.md`
- `docs/examples/dry-run-publishing.md`
- `docs/adr/0007-source-tiering-strategy.md`
- `docs/adr/0008-telegram-approval-gates.md`
- `docs/adr/0009-local-model-routing.md`
- `docs/adr/0010-publishing-adapter-strategy.md`

## Commands

- `make dev`
- `make lint`
- `make test`
- `make e2e`
- `make seed`
- `docker compose up --build`
