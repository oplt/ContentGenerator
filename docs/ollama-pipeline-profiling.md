# Ollama / ingestion pipeline profiling (ops Phase 11)

## Instrumentation

Stage timings (`cg.ingestion.stage.duration_ms` + `ingestion_stage` logs):

| Stage | Where |
|---|---|
| `source_fetch` | adapter fetch |
| `parsing` | adapter normalize |
| `normalization` | healthcheck (post-parse) |
| `database_reads` | recent raw articles |
| `deduplication` | key match + semantic skip |
| `database_writes` | insert + fetch_run finalize |
| `clustering` | embed + summarize + score |
| `total` | full `run_ingestion_workflow` |

Also stored on `fetch_run.metadata.stage_timings_ms` (no prompts/bodies).

Each Ollama generate/embed records `cg.llm.call.duration_ms` with
`provider`, `model`, `operation` (task name / `embed`) — never prompt text.

## Concurrency

**Problem:** `worker-io` concurrency 4 ran ingestion that calls Ollama
(embeddings + summarize) while `HTTP_PROVIDER_LLM_CONCURRENCY` defaulted to 4
→ many in-flight calls into one local Ollama process.

**Changes:**

1. Default `HTTP_PROVIDER_LLM_CONCURRENCY=1` (process-wide semaphore).
2. Move `enrichment` queue from `worker-io` → `worker-llm` (capped by
   `CELERY_WORKER_LLM_CONCURRENCY`, default 2, prefetch 1).
3. Synthetic matrix (`ollama_concurrency_bench.py`): with a serialized backend,
   concurrency **1** maximizes throughput; 2/4 only inflate mean latency.

**Recommendation:** keep LLM in-flight at **1** for a single local Ollama.
Raise to 2 only after measuring GPU headroom; avoid 4 on one host.

Note: `ingest_source` still performs embed/summarize on the ingestion path, but
**after** the persist session commits (`enrich_raw_articles_outside_db`). Stage
`clustering` timings cover that post-commit enrichment. Moving enrichment onto a
dedicated Celery `enrichment` queue remains optional capacity work.

## Tests

`backend/tests/test_phase11_ollama_pipeline.py`
