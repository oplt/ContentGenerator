#!/usr/bin/env python3
"""EXPLAIN (ANALYZE optional) for Phase 20 hot-path workflow queries.

Usage (Postgres):

  DATABASE_URL=postgresql+asyncpg://... \\
    PYTHONPATH=. backend/.venv/bin/python backend/scripts/explain_phase20_queries.py

  # With ANALYZE (runs queries; prefer a non-prod copy with representative data):
  PHASE20_EXPLAIN_ANALYZE=1 PYTHONPATH=. backend/.venv/bin/python \\
    backend/scripts/explain_phase20_queries.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text

QUERIES: list[tuple[str, str]] = [
    (
        "due_automations",
        """
        SELECT id FROM automations
        WHERE deleted_at IS NULL
          AND enabled IS TRUE
          AND trigger_type = 'schedule'
          AND next_run_at IS NOT NULL
          AND next_run_at <= NOW()
        ORDER BY next_run_at ASC
        LIMIT 50
        """,
    ),
    (
        "due_waits",
        """
        SELECT id FROM workflow_waits
        WHERE status = 'pending'
          AND wake_at IS NOT NULL
          AND wake_at <= NOW()
        ORDER BY wake_at ASC
        LIMIT 50
        """,
    ),
    (
        "ready_nodes",
        """
        SELECT id FROM workflow_node_runs
        WHERE status = 'ready'
        ORDER BY workflow_run_id, created_at ASC
        LIMIT 50
        """,
    ),
    (
        "expired_claims",
        """
        SELECT id FROM workflow_node_runs
        WHERE status IN ('running', 'queued')
          AND claim_expires_at IS NOT NULL
          AND claim_expires_at < NOW()
        ORDER BY claim_expires_at ASC
        LIMIT 50
        """,
    ),
    (
        "runs_by_tenant_status_date",
        """
        SELECT id FROM workflow_runs
        WHERE tenant_id = '00000000-0000-0000-0000-000000000001'
          AND status = 'succeeded'
        ORDER BY created_at DESC
        LIMIT 50
        """,
    ),
    (
        "nodes_by_run",
        """
        SELECT id FROM workflow_node_runs
        WHERE tenant_id = '00000000-0000-0000-0000-000000000001'
          AND workflow_run_id = '00000000-0000-0000-0000-000000000002'
        ORDER BY created_at ASC
        LIMIT 200
        """,
    ),
    (
        "publishing_by_account",
        """
        SELECT id FROM publishing_jobs
        WHERE tenant_id = '00000000-0000-0000-0000-000000000001'
          AND social_account_id = '00000000-0000-0000-0000-000000000003'
        ORDER BY created_at DESC
        LIMIT 50
        """,
    ),
    (
        "approvals_awaiting",
        """
        SELECT id FROM approval_requests
        WHERE status = 'pending'
          AND expires_at IS NOT NULL
          AND expires_at <= NOW()
        ORDER BY expires_at ASC
        LIMIT 50
        """,
    ),
    (
        "retention_finished_nodes",
        """
        SELECT id FROM workflow_node_runs
        WHERE finished_at IS NOT NULL
          AND status IN ('succeeded', 'failed', 'cancelled', 'skipped')
          AND finished_at < NOW() - INTERVAL '30 days'
        ORDER BY finished_at ASC
        LIMIT 200
        """,
    ),
]


async def main() -> int:
    from backend.db.session import SessionLocal

    analyze = os.environ.get("PHASE20_EXPLAIN_ANALYZE", "").strip() in {
        "1",
        "true",
        "yes",
    }
    prefix = "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)" if analyze else "EXPLAIN (FORMAT TEXT)"

    async with SessionLocal() as db:
        dialect = db.bind.dialect.name if db.bind is not None else "unknown"
        if dialect != "postgresql":
            print(f"skip: explain script expects postgresql (got {dialect})", file=sys.stderr)
            return 2
        for name, sql in QUERIES:
            print(f"\n=== {name} ===")
            result = await db.execute(text(f"{prefix}\n{sql}"))
            for row in result:
                print(row[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
