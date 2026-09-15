"""Seed disposable Postgres; capture Phase 0 EXPLAIN + checkout samples.

DATABASE_URL must target disposable Postgres (script refuses :5432).

    DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/content_generator \
      PYTHONPATH=. backend/.venv/bin/python \
      backend/tests/benchmarks/capture_sql_baseline.py
"""

from __future__ import annotations

import json
import os
import statistics
import time
from typing import Any
from urllib.parse import urlparse

import psycopg2

TENANT_ID = "00000000-0000-0000-0000-000000000001"
SAMPLE_COUNT = 10
RANDOM_SEED = 20260915

DUE_SOURCES_SQL = """
SELECT * FROM sources
WHERE active IS TRUE
  AND deleted_at IS NULL
  AND (next_poll_at IS NULL OR next_poll_at <= now())
ORDER BY next_poll_at ASC NULLS FIRST
LIMIT 500
"""

COLLISION_SQL = """
SELECT * FROM raw_articles
WHERE tenant_id = %(tenant_id)s
  AND deleted_at IS NULL
  AND (
    content_hash IN ('hash-1', 'hash-42')
    OR canonical_url IN ('https://example.test/1', 'https://example.test/42')
    OR dedupe_key IN ('key-1', 'key-42')
    OR title_normalized IN ('title 1', 'title 42')
  )
"""

ARTICLE_LIST_SQL = """
SELECT * FROM raw_articles
WHERE tenant_id = %(tenant_id)s
  AND deleted_at IS NULL
ORDER BY created_at DESC
LIMIT 100
"""

STALE_CLAIM_SQL = """
SELECT * FROM publishing_jobs
WHERE status IN ('claimed', 'running')
  AND claim_expires_at IS NOT NULL
  AND claim_expires_at <= now()
FOR UPDATE SKIP LOCKED
"""


def _dsn() -> str:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        raise SystemExit("DATABASE_URL is required")
    if raw.startswith("postgresql+asyncpg://"):
        raw = "postgresql://" + raw.removeprefix("postgresql+asyncpg://")
    parsed = urlparse(raw)
    if parsed.hostname in {"localhost", "127.0.0.1"} and (parsed.port or 5432) == 5432:
        raise SystemExit(
            "Refusing default shared port 5432. Use disposable Postgres (e.g. :55432)."
        )
    return raw


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction + 0.999)))
    return ordered[index]


def _plan_stats(plan: dict[str, Any]) -> dict[str, Any]:
    root = plan["Plan"]

    def walk_buffers_and_scans(node: dict[str, Any]) -> tuple[int, int, int]:
        removed = int(node.get("Rows Removed by Filter", 0))
        node_type = node.get("Node Type", "")
        scanned = 0
        if node_type in {"Seq Scan", "Index Scan", "Index Only Scan", "Bitmap Heap Scan"}:
            scanned = int(node.get("Actual Rows", 0)) + removed
        hit = int(node.get("Shared Hit Blocks", 0))
        read = int(node.get("Shared Read Blocks", 0))
        for child in node.get("Plans", []) or []:
            child_scanned, child_hit, child_read = walk_buffers_and_scans(child)
            scanned = max(scanned, child_scanned)
            hit += child_hit
            read += child_read
        return scanned, hit, read

    rows_scanned, hit_blocks, read_blocks = walk_buffers_and_scans(root)
    hit_blocks += int(plan.get("Shared Hit Blocks", 0))
    read_blocks += int(plan.get("Shared Read Blocks", 0))
    if rows_scanned == 0:
        rows_scanned = int(root.get("Actual Rows", 0))

    node = root.get("Node Type", "Unknown")
    children = root.get("Plans") or []
    if children:
        child_types = " + ".join(child.get("Node Type", "?") for child in children)
        node = (
            f"{child_types} / {root['Node Type']}"
            if root.get("Node Type") in {"Limit", "LockRows", "Sort"}
            else f"{node} + {child_types}"
        )
    return {
        "node": node,
        "execution_ms": round(float(plan.get("Execution Time", 0.0)), 3),
        "actual_rows": int(root.get("Actual Rows", 0)),
        "rows_scanned": rows_scanned,
        "shared_hit_blocks": hit_blocks,
        "shared_read_blocks": read_blocks,
        "planning_ms": round(float(plan.get("Planning Time", 0.0)), 3),
    }


def _seed(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE raw_articles, sources, publishing_jobs, tenants CASCADE")
        cur.execute(
            """
            INSERT INTO tenants (id, name, slug, status, plan_tier, timezone, settings)
            VALUES (%s, 'Phase0', 'phase0', 'active', 'starter', 'UTC', '{}'::json)
            """,
            (TENANT_ID,),
        )
        cur.execute(
            """
            INSERT INTO sources (
              id, tenant_id, name, source_type, url, parser_type, category,
              category_tags, region_tags, language_tags, source_tier, content_vertical,
              freshness_decay_hours, legal_risk, tier1_confirmation_required,
              config, polling_config, parser_config, polling_interval_minutes,
              trust_score, active, robots_respected, failure_count, success_count,
              circuit_state, stale_cache_ttl_seconds, version, next_poll_at
            )
            SELECT
              md5('source-' || n)::uuid,
              %s::uuid,
              'source-' || n,
              'rss',
              'https://example.test/feed/' || n,
              'auto',
              'general',
              '[]'::json,
              '[]'::json,
              '[]'::json,
              'signal',
              'general',
              24,
              false,
              false,
              '{}'::json,
              '{}'::json,
              '{}'::json,
              30,
              0.8,
              true,
              true,
              0,
              n,
              'closed',
              3600,
              1,
              CASE WHEN n %% 2 = 0 THEN now() - interval '1 minute' ELSE NULL END
            FROM generate_series(1, 100) AS n
            """,
            (TENANT_ID,),
        )
        cur.execute(
            """
            INSERT INTO raw_articles (
              id, tenant_id, source_id, url, canonical_url, dedupe_key,
              title_normalized, content_hash, title, extraction_confidence,
              metadata, created_at, updated_at
            )
            SELECT
              md5('article-' || n)::uuid,
              %s::uuid,
              md5('source-' || ((n - 1) %% 100 + 1))::uuid,
              'https://example.test/' || n,
              'https://example.test/' || n,
              'key-' || n,
              'title ' || n,
              'hash-' || n,
              'Article ' || n,
              0.5,
              '{}'::json,
              now() - ((10000 - n) || ' seconds')::interval,
              now()
            FROM generate_series(1, 10000) AS n
            """,
            (TENANT_ID,),
        )
        cur.execute("ANALYZE sources")
        cur.execute("ANALYZE raw_articles")
        cur.execute("ANALYZE publishing_jobs")
    conn.commit()


def _explain(conn: Any, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    statement = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"
    with conn.cursor() as cur:
        cur.execute(statement, params or {})
        row = cur.fetchone()
    assert row is not None
    payload = row[0]
    plan = payload[0] if isinstance(payload, list) else payload
    return _plan_stats(plan)


def _checkout_samples(dsn: str) -> dict[str, Any]:
    samples: list[float] = []
    for _ in range(SAMPLE_COUNT):
        started = time.perf_counter_ns()
        conn = psycopg2.connect(dsn, connect_timeout=5)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            conn.close()
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    return {
        "p50_ms": round(_percentile(samples, 0.50), 3),
        "p95_ms": round(_percentile(samples, 0.95), 3),
        "p99_ms": round(_percentile(samples, 0.99), 3),
        "samples_ms": [round(sample, 3) for sample in samples],
        "mean_ms": round(statistics.fmean(samples), 3),
    }


def main() -> None:
    dsn = _dsn()
    conn = psycopg2.connect(dsn)
    try:
        _seed(conn)
        plans = {
            "due_sources": {
                "command": f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {DUE_SOURCES_SQL.strip()}",
                **_explain(conn, DUE_SOURCES_SQL),
            },
            "bulk_collision_lookup": {
                "command": (
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM raw_articles "
                    "WHERE tenant_id=:tenant_id AND deleted_at IS NULL AND "
                    "(content_hash IN (:hashes) OR canonical_url IN (:urls) OR "
                    "dedupe_key IN (:keys) OR title_normalized IN (:titles))"
                ),
                **_explain(conn, COLLISION_SQL, {"tenant_id": TENANT_ID}),
            },
            "raw_article_list": {
                "command": (
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM raw_articles "
                    "WHERE tenant_id=:tenant_id AND deleted_at IS NULL "
                    "ORDER BY created_at DESC LIMIT 100"
                ),
                **_explain(conn, ARTICLE_LIST_SQL, {"tenant_id": TENANT_ID}),
            },
            "stale_claim_scan": {
                "command": f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {STALE_CLAIM_SQL.strip()}",
                **_explain(conn, STALE_CLAIM_SQL),
            },
        }
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM sources")
            source_count = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM raw_articles")
            article_count = cur.fetchone()[0]
    finally:
        conn.close()

    checkout = _checkout_samples(dsn)
    print(
        json.dumps(
            {
                "random_seed": RANDOM_SEED,
                "tenant_id": TENANT_ID,
                "source_count": source_count,
                "article_count": article_count,
                "connection_checkout_ms": checkout,
                "sql_plans": plans,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
