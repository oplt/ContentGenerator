# ADR 0007: Tiered Source Strategy

## Status
Accepted

## Context
Trend discovery and publish safety depend on treating authoritative reporting, weak signals, and amplification chatter differently. A flat source model overweights noisy sources and underweights authoritative confirmation.

## Decision
Use a tiered source strategy:

- Tier 1: authoritative sources for politics, conflicts, economy, and company/official claims
- Tier 2: signal sources for trend discovery such as Reddit, blogs, RSS feeds, and newsletters
- Tier 3: amplification sources such as social chatter and other weak-signal discussions

Source reliability, vertical, and risk policy are persisted and used by scoring and gating logic.

## Consequences

Positive:

- High-risk topics can require stronger confirmation before editorial approval
- Weak-signal sources remain useful without driving publication decisions alone
- The scoring model becomes more explainable

Trade-offs:

- Connector setup and source maintenance become more operationally involved
- Editorial and scoring services must understand source tiers consistently
