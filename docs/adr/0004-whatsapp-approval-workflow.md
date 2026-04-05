# ADR 0004: WhatsApp As The Human Approval Channel

## Status
Accepted

## Context
The core product promise is that drafts are routed to operators where they already respond quickly. Email is too slow, dashboard-only approval misses mobile behavior, and approvals must support conversational revision loops.

## Decision
Use WhatsApp as the primary approval channel for v1.

Implementation details:

- approval requests are first-class records in PostgreSQL
- outgoing and incoming messages are stored with parsed intent and raw payload references
- the provider abstraction defaults to a local stub and supports Meta WhatsApp Cloud API when configured
- revision messages regenerate content and resend the updated draft
- publishing only starts on explicit approval

## Consequences

Positive:

- Human-in-the-loop flow matches how operators actually respond
- Approval and revision history is fully auditable
- Stub mode keeps local development unblocked

Trade-offs:

- Webhook verification and payload parsing become correctness-critical
- Message UX must remain concise because the medium is constrained
