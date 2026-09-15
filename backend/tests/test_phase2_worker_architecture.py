"""Phase 2 — local worker resource and queue contracts."""

from pathlib import Path


def test_local_worker_matches_worker_db_capacity() -> None:
    procfile = Path(__file__).parents[2] / "Procfile.dev"
    worker_command = next(line for line in procfile.read_text().splitlines() if line.startswith("worker:"))

    assert "--pool=gevent" in worker_command
    assert "--concurrency=4" in worker_command
    assert "--prefetch-multiplier=1" in worker_command
    assert "--queues=ingestion,enrichment,generation,video,approvals,publishing,analytics,email" in worker_command
