# Implementation Report

## Current Architecture

SignalForge is a modular FastAPI and React monolith with explicit workflow stages:

- Source ingestion normalizes RSS, Reddit, sitemap, official feed, and optional trend connectors into candidate stories.
- Story intelligence clusters and scores candidates before editorial brief generation.
- Editorial briefs, asset approvals, and publish approvals are routed through Telegram-first operator gates.
- Content generation uses a task-aware inference abstraction that supports local Ollama, local vLLM, local llama.cpp, and OpenAI-compatible endpoints.
- Fact, risk, and policy review blocks unsafe output before approval and publishing.
- Media rendering produces text, image, preview clip, thumbnail, subtitles, voiceover, and multi-aspect-ratio video outputs.
- Publishing uses adapter-based providers with dry-run support, retries, idempotency keys, and queue recovery actions.
- Analytics normalizes cross-platform post metrics and feeds them back into ranking and generation decisions.

## Shipped Capabilities

- Telegram-first approval flow for topic, brief, asset, and publish decisions
- Local-model abstraction with provider health checks and task-specific routing
- Fact/risk review persisted into content and approval records
- FFmpeg-oriented media rendering with previews and thumbnails
- Unified publishing queue with X and Bluesky live adapters plus dry-run support for additional platforms
- Analytics overview endpoints for hooks, timing, brand performance, conversion, and learning logs
- Operator API surface for source control, approvals, queue recovery, connected accounts, and health/readiness
- Admin UI pages for dashboard, sources, stories, approvals, publishing queue, connected accounts, and settings

## Security and Config Status

- Production bootstrap now requires explicit strong values for `JWT_SECRET`, `CSRF_SECRET`, `ENCRYPTION_KEY`, `TELEGRAM_WEBHOOK_SECRET`, and `TELEGRAM_CALLBACK_SIGNING_SECRET`.
- Cookie-authenticated refresh/logout flows now require a double-submit CSRF token and stricter cookie settings.
- Telegram and WhatsApp inbound approval flows both verify authenticity and dedupe replays.
- Social publishing credentials and messaging credentials support encrypted storage plus external secret references through `EXTERNAL_SECRET_REFERENCES_JSON`.
- API responses now expose RBAC placeholders so multi-role tenancy can be expanded without breaking clients.

## Blocked or Partial External Dependencies

- Real social platform support is still uneven. X and Bluesky are the most complete end-to-end adapters in the repo.
- FFmpeg and ffprobe must be available on the host for full media-render verification.
- Telegram webhook registration requires a public HTTPS `PUBLIC_URL`.
- Local model quality and throughput depend on local GPU availability and external model downloads.
- Optional trend connectors remain best-effort and may degrade when upstream products or policies change.

## Production-Hardening Roadmap

1. Replace `EXTERNAL_SECRET_REFERENCES_JSON` with Vault, AWS Secrets Manager, or another managed backend.
2. Expand RBAC from placeholder claims into enforced operator/admin/editor roles per route group.
3. Add rate limiting and more explicit audit coverage for auth, webhook, and publish-control endpoints.
4. Add end-to-end integration tests for Telegram callbacks, CSRF rotation, and queue recovery flows.
5. Add provider certification and operational dashboards for each live publishing adapter.
