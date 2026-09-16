"""CLI wrapper for route latency log analysis."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.tests.benchmarks.analyze_route_latencies import compare_routes, summarize_durations_ms
from backend.tests.benchmarks.analyze_route_latencies import extract_route_durations_ms


def main() -> None:
    repo = Path(__file__).resolve().parents[3]
    log_paths = sorted((repo / "logs").glob("app_*.log"))
    report = {
        "social_accounts": summarize_durations_ms(
            extract_route_durations_ms(
                log_paths,
                route_substring="/api/v1/publishing/social-accounts",
            )
        ),
        "compare_health_live": compare_routes(
            log_paths,
            suspect_route="/api/v1/publishing/social-accounts",
            baseline_route="/api/v1/health/live",
        ),
    }
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
