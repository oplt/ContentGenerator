"""Parse backend.request JSON logs and summarize route latency (ops Phase 15)."""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction + 0.999)))
    return ordered[index]


def extract_route_durations_ms(
    log_paths: list[Path],
    *,
    route_substring: str,
    method: str = "GET",
) -> list[float]:
    """Collect duration_ms for matching request_complete events."""
    durations: list[float] = []
    for path in log_paths:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "request_complete" not in line or route_substring not in line:
                continue
            inner: dict[str, object] | None = None
            try:
                outer = json.loads(line)
                raw_message = outer.get("message")
                if isinstance(raw_message, str):
                    parsed = json.loads(raw_message)
                    if isinstance(parsed, dict):
                        inner = parsed
            except json.JSONDecodeError:
                inner = None
            if inner is None:
                match = re.search(r'"duration_ms":\s*([0-9.]+)', line)
                if match is not None:
                    durations.append(float(match.group(1)))
                continue
            if inner.get("method") != method:
                continue
            route = inner.get("route") or inner.get("path")
            if not isinstance(route, str) or route_substring not in route:
                continue
            raw = inner.get("duration_ms")
            if isinstance(raw, (int, float)):
                durations.append(float(raw))
    return durations


def summarize_durations_ms(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    return {
        "count": len(values),
        "p50_ms": round(statistics.median(values), 2),
        "p95_ms": round(_percentile(values, 0.95), 2),
        "max_ms": round(max(values), 2),
    }


def compare_routes(
    log_paths: list[Path],
    *,
    suspect_route: str,
    baseline_route: str,
) -> dict[str, object]:
    suspect = summarize_durations_ms(
        extract_route_durations_ms(log_paths, route_substring=suspect_route)
    )
    baseline = summarize_durations_ms(
        extract_route_durations_ms(log_paths, route_substring=baseline_route)
    )
    return {"suspect": suspect, "baseline": baseline}
