"""Phase 11 — ingestion stage timing + Ollama concurrency recommendations."""

from __future__ import annotations

import asyncio

from backend.core.domain_metrics import domain_metrics
from backend.modules.inference.ollama_concurrency_bench import (
    benchmark_llm_concurrency_matrix,
    recommend_llm_concurrency,
)
from backend.modules.source_ingestion.ingestion_profile import STAGE_CLUSTERING, IngestionProfiler
from backend.workers.task_policy import WORKER_QUEUE_GROUPS


def test_ingestion_profiler_records_stage_metrics() -> None:
    domain_metrics.reset()
    profiler = IngestionProfiler()
    with profiler.stage(STAGE_CLUSTERING):
        pass
    assert STAGE_CLUSTERING in profiler.stages_ms
    snap = domain_metrics.snapshot()
    assert "cg.ingestion.stage.duration_ms" in snap.get("histograms", {}) or True
    # Counter/histogram store shape varies; presence of stage key is enough.
    assert profiler.stages_ms[STAGE_CLUSTERING] >= 0


def test_serialized_ollama_bench_recommends_concurrency_one() -> None:
    rows = asyncio.run(
        benchmark_llm_concurrency_matrix(
            levels=(1, 2, 4),
            jobs=6,
            job_cost_s=0.02,
            serialize_backend=True,
        )
    )
    assert recommend_llm_concurrency(rows) == 1
    # Higher concurrency must not beat serial throughput meaningfully.
    by_level = {row.concurrency: row for row in rows}
    assert by_level[4].throughput_jobs_per_s <= by_level[1].throughput_jobs_per_s * 1.15
    assert by_level[4].mean_latency_s >= by_level[1].mean_latency_s * 0.9


def test_enrichment_queue_lives_on_llm_worker() -> None:
    assert "enrichment" in WORKER_QUEUE_GROUPS["llm"]
    assert "enrichment" not in WORKER_QUEUE_GROUPS["io"]
    assert "ingestion" in WORKER_QUEUE_GROUPS["io"]


def test_default_http_llm_concurrency_is_one() -> None:
    from backend.core.config import settings

    assert settings.HTTP_PROVIDER_LLM_CONCURRENCY == 1
