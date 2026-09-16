# Prevent unnecessary LLM calls (ops Phase 12)

## Ingestion enrichment cost

Per new article, clustering previously always called:

1. **Ollama embeddings** (`title\\nbody`)
2. **Ollama summarize** (new cluster only)

Worthiness scoring is heuristic-only (no LLM). Embed + summarize use different
models/endpoints — **not combined** into one structured call (would hurt embed
quality / maintainability).

## Cache

`backend/modules/inference/enrichment_cache.py` via tenant Redis cache:

| Field | Role |
|---|---|
| `enrichment_content_hash(title, body)` | URL-independent text fingerprint |
| `operation` | `embed` / `summarize` |
| `model` | embeddings or LLM model id |
| `prompt_version` | `embed.v1…` / `summarize.v1.max_words=N` |

TTL: `LLM_ENRICHMENT_CACHE_TTL_SECONDS` (default 7d). Singleflight avoids stampedes.
Fail-open if Redis is down.

Bump `SUMMARIZE_PROMPT_VERSION` / `EMBED_INPUT_VERSION` when prompt framing changes
so stale results are not reused.

## Already avoided

* Re-normalize of same `raw_article_id` short-circuits before embed
* Near-duplicate semantic match reuses existing normalized row (after one embed)

## Tests

`backend/tests/test_enrichment_llm_cache.py`
