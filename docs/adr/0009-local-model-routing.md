# ADR 0009: Local Model Routing Strategy

## Status
Accepted

## Context
The system needs local-first inference while remaining portable across different serving backends. Planner, writer, and reviewer tasks also have different model-quality and latency needs.

## Decision
Route inference through a common provider interface with task-aware model selection and backend swappability.

Supported backends:

- Ollama
- vLLM
- llama.cpp
- generic OpenAI-compatible endpoints

Routing rules:

- task classes may use different models
- structured JSON tasks should prefer stronger schema-compatible backends
- fallback order is configuration-driven
- local-first remains the default deployment posture

## Consequences

Positive:

- The system can run on a wide range of hardware and deployment modes
- Task-specific model routing becomes explicit
- Future provider swaps do not require domain-layer rewrites

Trade-offs:

- Provider health and parse reliability must be monitored carefully
- More configuration is required to keep task routing coherent
