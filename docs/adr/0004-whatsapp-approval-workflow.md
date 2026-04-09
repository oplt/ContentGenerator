# ADR 0004: Legacy WhatsApp Approval Fallback

## Status
Superseded by ADR 0008

## Context
The repository initially shipped with WhatsApp as the primary approval surface. The product direction is now Telegram-first with multi-stage approval gates, but some tenants may still need WhatsApp as a secondary or legacy delivery channel.

## Decision
Retain WhatsApp as an optional fallback channel, not the primary editorial approval system.

Implementation details:

- approval requests are first-class records in PostgreSQL
- outgoing and incoming messages are stored with parsed intent and raw payload references
- the provider abstraction defaults to a local stub and supports Meta WhatsApp Cloud API when configured
- revision messages regenerate content and resend the updated draft
- publishing only starts on explicit approval

## Consequences

Positive:

- Backward compatibility remains available for legacy tenants
- Approval and revision history stays auditable across channels
- Stub mode keeps local development unblocked

Trade-offs:

- The codebase must support two approval transports
- Telegram remains the primary editorial UX, so WhatsApp should not drive product decisions
