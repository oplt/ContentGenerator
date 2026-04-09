# ADR 0010: Publishing Adapter Strategy

## Status
Accepted

## Context
Publishing APIs vary widely in auth, media upload behavior, scheduling capabilities, and analytics support. The product cannot bind domain logic directly to a single platform’s API shape.

## Decision
Use adapter-based publishing integrations with a normalized internal contract and dry-run support.

Each adapter should support, over time:

- auth validation
- draft creation
- publish now
- application-level scheduling or native scheduling
- external URL lookup
- metrics fetch
- delete/unpublish where available

The repository keeps legacy-compatible provider implementations while moving product language toward `publish jobs` and `connected accounts`.

## Consequences

Positive:

- Platform-specific complexity stays isolated
- Dry-run and partial-capability deployments remain possible
- Retry and dead-letter handling can be standardized above the adapters

Trade-offs:

- Capability mismatches must be surfaced explicitly
- Some platforms will remain only partially implemented until credentials and reviews are available
