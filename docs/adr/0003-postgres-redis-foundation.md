# ADR 0003: PostgreSQL And Redis As The Operational Foundation

## Status
Accepted

## Context
The product needs one durable source of truth for multi-tenant workflow state plus a fast ephemeral system for queues, rate limits, cache fallback, idempotency helpers, and short-lived approval/auth tokens.

## Decision
Use PostgreSQL for transactional state and Redis for ephemeral coordination.

PostgreSQL owns:

- tenants, memberships, roles, permissions
- ingestion state, normalized articles, clusters, scores
- content plans, jobs, revisions, assets
- approvals, publishing jobs, published posts, analytics snapshots, audit logs, task executions

Redis owns:

- Celery broker/result backend
- rate limiting counters
- verification/password reset/MFA tokens
- stale response cache and negative cache state

## Consequences

Positive:

- Strong consistency for business state
- Simple query model for dashboards and audit trails
- Fast transient coordination without introducing another service category

Trade-offs:

- Redis becomes important to both async work and request-time protections
- JSON-heavy feature growth still needs discipline to avoid unbounded blob usage
