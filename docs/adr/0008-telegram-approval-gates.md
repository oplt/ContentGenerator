# ADR 0008: Telegram-First Approval Gates

## Status
Accepted

## Context
The product is a semi-autonomous editorial system, not a blind auto-posting bot. Operators need fast mobile approvals with structured callbacks and auditability.

## Decision
Use Telegram as the primary approval channel and enforce explicit approval gates across the workflow.

Primary approval flow:

1. Topic / brief approval
2. Asset approval
3. Publish approval

Implementation rules:

- callback payloads must be signed
- approval requests must be persisted
- callback processing must be idempotent
- expirations and audit trails must be recorded
- WhatsApp remains optional fallback only

## Consequences

Positive:

- The product is aligned with fast operator response behavior
- Approval history is auditable and structured
- Telegram becomes the canonical UX for editorial control

Trade-offs:

- Callback correctness and secret handling are operationally critical
- Multi-stage approvals increase workflow complexity
