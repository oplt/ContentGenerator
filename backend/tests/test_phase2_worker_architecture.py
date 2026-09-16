"""Phase 2 — local worker resource and queue contracts."""

from pathlib import Path


def _procfile_lines() -> list[str]:
    return (Path(__file__).parents[2] / "Procfile.dev").read_text().splitlines()


def test_local_workers_are_split_by_workload() -> None:
    lines = _procfile_lines()
    by_name = {
        line.split(":", 1)[0]: line
        for line in lines
        if line and not line.startswith("#") and ":" in line
    }

    assert "worker_io" in by_name
    assert "worker_llm" in by_name
    assert "worker_media" in by_name
    assert "worker_publishing" in by_name
    assert "worker_db" in by_name
    assert "worker" not in by_name

    assert "--queues=ingestion,email,approvals" in by_name["worker_io"]
    assert "--pool=gevent" in by_name["worker_io"]
    assert "--concurrency=4" in by_name["worker_io"]

    assert "--queues=generation,enrichment" in by_name["worker_llm"]
    assert "--concurrency=2" in by_name["worker_llm"]

    assert "--queues=video" in by_name["worker_media"]
    assert "--pool=prefork" in by_name["worker_media"]
    assert "--concurrency=1" in by_name["worker_media"]

    assert "--queues=publishing" in by_name["worker_publishing"]
    assert "--queues=analytics" in by_name["worker_db"]


def test_frontend_and_workers_wait_for_api_liveness() -> None:
    text = "\n".join(_procfile_lines())
    assert "api/v1/health/live" in text
    frontend = next(line for line in _procfile_lines() if line.startswith("frontend:"))
    assert "health/live" in frontend
    assert "npm run dev" in frontend


def test_alembic_runs_only_on_backend_process() -> None:
    lines = [line for line in _procfile_lines() if line and not line.startswith("#")]
    alembic_lines = [line for line in lines if "alembic" in line]
    assert len(alembic_lines) == 1
    assert alembic_lines[0].startswith("backend:")
