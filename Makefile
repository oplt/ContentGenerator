SHELL := /bin/bash

.PHONY: dev infra-up infra-down backend-dev worker-dev frontend-dev lint test e2e seed build

dev: infra-up
	@echo "Start backend with: make backend-dev"
	@echo "Start worker with: make worker-dev"
	@echo "Start frontend with: make frontend-dev"

infra-up:
	docker compose up -d postgres redis minio

infra-down:
	docker compose down

backend-dev:
	cd backend && .venv/bin/alembic upgrade head && .venv/bin/uvicorn backend.api.main:app --reload

worker-dev:
	cd backend && .venv/bin/celery -A backend.workers.celery_app:celery_app worker --loglevel=INFO --queues=ingestion,enrichment,generation,video,approvals,publishing,analytics,email

frontend-dev:
	cd frontend && npm run dev

lint:
	cd backend && .venv/bin/ruff check .
	cd frontend && npm run lint

test:
	cd backend && .venv/bin/pytest
	cd frontend && npm run test

e2e:
	cd frontend && npx playwright install chromium
	cd frontend && npm run e2e -- --project=chromium

seed:
	cd backend && .venv/bin/python -m backend.scripts.seed_demo

build:
	cd frontend && npm run build
