"""Print repeatable CPU/memory samples used by the Phase 0 baseline.

Run from the repository root:
    PYTHONPATH=. backend/.venv/bin/python \
      backend/tests/benchmarks/capture_seeded_microbenchmarks.py
"""

from __future__ import annotations

import json
import statistics
import time
import tracemalloc
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import orjson

from backend.modules.analytics.metrics import AnalyticsMetrics
from backend.modules.content_generation.service import ContentGenerationService
from backend.modules.publishing.attempt_lifecycle import PublishAttemptLifecycle
from backend.modules.source_ingestion.adapters import canonicalize_url, normalize_title
from backend.modules.source_ingestion.repository import ArticleDedupeKeys, SourceRepository
from backend.modules.source_ingestion.service import SourceIngestionService
from backend.modules.story_intelligence.scoring import ClusterScorer

RANDOM_SEED = 20260915
SAMPLE_COUNT = 10


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction + 0.999)))
    return ordered[index]


def _measure(operation: Callable[[], object]) -> dict[str, object]:
    operation()
    samples: list[float] = []
    peaks: list[float] = []
    for _ in range(SAMPLE_COUNT):
        tracemalloc.start()
        started = time.perf_counter_ns()
        operation()
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peaks.append(peak / 1_048_576)
    return {
        "latency": {
            "p50_ms": round(_percentile(samples, 0.50), 3),
            "p95_ms": round(_percentile(samples, 0.95), 3),
            "p99_ms": round(_percentile(samples, 0.99), 3),
        },
        "peak_memory_mb": round(statistics.median(peaks), 3),
        "samples_ms": [round(sample, 3) for sample in samples],
    }


TITLES = [f"Breaking: Seeded Article {index}?utm_source=phase0" for index in range(1000)]
DEDUPE_ROWS = [
    SimpleNamespace(
        content_hash=f"hash-{index}",
        canonical_url=f"https://example.test/{index}",
        dedupe_key=f"key-{index}",
        title_normalized=f"title {index}",
    )
    for index in range(1000)
]
DEDUPE_CANDIDATES = [
    ArticleDedupeKeys(
        content_hash=f"hash-{index * 10}",
        canonical_url=f"https://candidate.test/{index}",
        dedupe_key=f"candidate-{index}",
        title_normalized=f"candidate {index}",
    )
    for index in range(100)
]
HEALTH_ROWS = [
    SimpleNamespace(success_count=index + 1, failure_count=index % 7, trust_score=0.8)
    for index in range(100)
]
TEXTS = [
    f"Seeded technology market story {index} with deterministic company evidence and analysis"
    for index in range(100)
]
POSTS = [SimpleNamespace(id=index, platform="x") for index in range(100)]
JOBS = [SimpleNamespace(idempotency_key=f"seeded-job-{index}") for index in range(100)]
PAYLOADS = [
    {"id": index, "created_at": f"2026-09-15T12:{index % 60:02}:00Z", "status": "active"}
    for index in range(1000)
]


def _source_ingestion() -> object:
    return [
        (
            normalize_title(title),
            canonicalize_url(f"https://EXAMPLE.test/{index}/?utm_source=x"),
        )
        for index, title in enumerate(TITLES)
    ]


def _duplicate_detection() -> object:
    return SourceRepository._match_candidates_to_rows(
        cast(Any, DEDUPE_CANDIDATES),
        cast(Any, DEDUPE_ROWS),
    )


def _source_health() -> object:
    return [
        SourceIngestionService._recompute_trust_score(cast(Any, row))
        for row in HEALTH_ROWS
    ]


def _story_clustering() -> object:
    scorer = object.__new__(ClusterScorer)
    return [scorer._extract_keywords(text) for text in TEXTS]


def _content_generation() -> object:
    service = object.__new__(ContentGenerationService)
    return [
        (service._trim(text * 8, 280), service._build_hashtags("seeded topic", "aggressive"))
        for text in TEXTS
    ]


def _publishing_claim_recovery() -> object:
    return [
        PublishAttemptLifecycle.build_attempt_key(cast(Any, job), 1 + index % 3)
        for index, job in enumerate(JOBS)
    ]


def _analytics_sync() -> object:
    return [AnalyticsMetrics.synthetic_metrics(post) for post in POSTS]


def _major_list_endpoints() -> object:
    return orjson.loads(orjson.dumps(PAYLOADS))


OPERATIONS: dict[str, Callable[[], object]] = {
    "source_ingestion": _source_ingestion,
    "duplicate_detection": _duplicate_detection,
    "source_health": _source_health,
    "story_clustering": _story_clustering,
    "content_generation": _content_generation,
    "publishing_claim_recovery": _publishing_claim_recovery,
    "analytics_sync": _analytics_sync,
    "major_list_endpoints": _major_list_endpoints,
}


if __name__ == "__main__":
    output = {
        "random_seed": RANDOM_SEED,
        "sample_count": SAMPLE_COUNT,
        "scenarios": {name: _measure(operation) for name, operation in OPERATIONS.items()},
    }
    print(json.dumps(output, indent=2))
