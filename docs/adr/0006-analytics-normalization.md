# ADR 0006: Analytics Normalization Strategy

## Status
Accepted

## Context
Publishing targets expose incompatible metrics and payload formats. The dashboard still needs comparable trend lines across platform, tenant, topic, and content format.

## Decision
Normalize analytics into daily post-level snapshots and aggregate in application queries.

The canonical fields are:

- impressions
- views
- likes
- comments
- shares
- watch time
- CTR when available
- platform/topic/content format labels

Raw provider payloads are still stored for audit and future enrichment, but dashboards read from the normalized snapshot model.

## Consequences

Positive:

- Cross-platform reporting stays consistent
- Backfills and provider-specific parsing changes do not require frontend rewrites
- Feedback signals can be reused in content scoring over time

Trade-offs:

- Some platform nuance is flattened
- Snapshot jobs must be idempotent and clearly versioned when parsing evolves
