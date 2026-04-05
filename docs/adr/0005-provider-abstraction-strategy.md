# ADR 0005: Provider Abstraction Strategy

## Status
Accepted

## Context
The product touches unstable and uneven external surfaces: LLMs, embeddings, TTS, captioning, WhatsApp, and several social publishing APIs with different capability limits.

## Decision
Standardize each external surface behind narrow provider interfaces and keep stub providers as first-class implementations.

Key interfaces:

- `LLMProvider`, `EmbeddingsProvider`
- `ResearchProvider`, `ScriptProvider`, `VisualProvider`, `VoiceProvider`, `CaptionProvider`, `RenderService`
- `WhatsAppProvider`
- per-platform publishing providers

The default configuration favors:

- mock LLM/embedding behavior for local determinism
- stub WhatsApp delivery
- stub publishing providers or manual fallback when real capabilities are not available

## Consequences

Positive:

- The product can ship real workflows before all provider credentials exist
- Capability flags and manual fallback states remain explicit
- Future provider swaps do not require dashboard or domain-model rewrites

Trade-offs:

- Interface discipline matters; leaking provider-specific details would erode the abstraction quickly
