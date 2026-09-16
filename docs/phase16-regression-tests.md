# Phase 16 — regression test matrix

Automated ownership map: `backend/tests/test_phase16_regression_matrix.py`.

## Prompt minimum coverage

| Requirement | Owning tests |
|---|---|
| Migrations empty DB → head | `test_migration_drift.test_alembic_upgrade_head_on_disposable_db` |
| Migrations previous → head | `test_migration_drift.test_alembic_upgrade_from_previous_revision` |
| Alembic at head | `test_migration_drift`, `test_schema_revision` |
| Workflow tables exist | `test_migration_drift.test_workflow_tables_exist_after_upgrade` |
| List definitions / automations / runs | `test_workflow_listings_regression.py` |
| Scheduler tick | `test_workflow_scheduler.test_tick_creates_occurrence_and_run` |
| No double claim | `test_workflow_scheduler` + `test_workflow_scheduler_pg` |
| Tenant isolation | workflow domain + strategy + account selection tests |
| Soft-delete filters | `test_workflow_listings_regression` (social accounts) |
| Correlation ID | `test_correlation_id_propagation.py` |
| Tenant on errors | `test_tenant_context_on_errors.py` |
| FE no retry 400/401/403 | `frontend/src/lib/queryRetry.test.ts` |
| GET dedupe policy | `frontend/src/lib/queryClient.test.ts` (moderate `staleTime`) |
| Briefs RBAC | `test_briefs_write_permission.py`, `access.test.ts` |
| Audit logs contract | `test_audit_logs_http.py` |
| Ingestion idempotency | phase 3/14 + scheduling dedupe tests |
| Enrichment cache keys | `test_enrichment_llm_cache.py` |
| DB TX outside LLM | `test_phase13_db_tx_lifetime.py` |

## CI commands

```bash
make check
make regression-unit
make regression-integration   # requires CG_RUN_DB_MIGRATIONS=1 + Postgres
cd frontend && npm test -- --run && npm run build
```

Integration migration tests are skipped locally unless `CG_RUN_DB_MIGRATIONS=1`.
