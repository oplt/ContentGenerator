# DB transaction lifetime around external calls (ops Phase 13)

## Anti-pattern

```text
open session/TX
→ write/lock rows
→ await Ollama / HTTP (5–25s)
→ write again
→ commit
```

That holds asyncpg pool checkouts and row locks for the full LLM latency,
amplifying pool exhaustion when ingestion and generation overlap.

## Target pattern

```text
short read/claim TX → commit/close
→ external I/O (no DB connection)
→ short persist TX → commit/close
```

Idempotency / state transitions keep correctness across the gap
(e.g. fetch_run status, content job `pipeline_stage`, normalized-by-raw uniqueness).

## Paths audited

| Path | Status |
|---|---|
| Ingestion network fetch | Already split (`prepare` → fetch → `persist`) via `session_scope` + `run_detached_async_task` |
| Ingestion clustering (embed/summarize) | **Fixed:** `persist_success_body` returns raw IDs only; `enrich_raw_articles_outside_db` runs after commit |
| Content generation | Mid-pipeline `commit()` after prepare for durability; worker uses detached ledger. **Residual:** same `AsyncSession` stays checked out during LLM until the entrypoint session closes |
| Editorial briefs | **Residual:** request-scoped `get_db` session spans structured LLM call |
| Workflow LLM nodes | **Residual:** executor session spans node LLM/image/TTS work |
| Image/TTS Celery tasks | Still use `run_async_task` (one session for provider I/O) |

## Ingestion clustering fix

1. `persist_success_body` — DB-only: dedupe, insert raw articles, finalize fetch_run. No Ollama.
2. Session exits (`session_scope` commit+close).
3. `enrich_raw_articles_outside_db` — per article:
   - short load snap
   - embed/summarize **outside** any session (Redis enrichment cache still applies)
   - short persist (normalize + cluster + score)

`ClusterPipelineMixin.process_articles` now raises if called; it previously held `self.db` across LLM.

## Pool notes

* Ingest workers: `run_detached_async_task` closes the ops ledger session before the workflow.
* Clustering no longer nests Ollama inside the persist checkout → fewer concurrent checkouts per article batch.
* Content-gen / briefs residuals still consume one pool connection for LLM duration on those entrypoints; prefer Celery + further split-phase if pool wait metrics rise.

## Tests

`backend/tests/test_phase13_db_tx_lifetime.py`
