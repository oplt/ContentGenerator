"""Phase 7: source ingestion is queued instead of performed in the API request."""

import ast
from pathlib import Path


ROUTER_PATH = Path(__file__).parents[1] / "modules/source_ingestion/router.py"
TASK_PATH = Path(__file__).parents[1] / "workers/task_defs/ingestion.py"


def _function(source_path: Path, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    tree = ast.parse(source_path.read_text())
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name
    )


def test_manual_ingestion_routes_enqueue_and_return_202() -> None:
    source = ROUTER_PATH.read_text()
    ingest = _function(ROUTER_PATH, "ingest_source")
    manual_poll = _function(ROUTER_PATH, "manual_poll_source")

    assert '@router.post("/{source_id}/ingest", response_model=IngestionTriggerResponse, status_code=202)' in source
    assert "run_ingestion_workflow" not in ast.unparse(ingest)
    assert "_enqueue_source_ingestion" in ast.unparse(ingest)
    assert "_enqueue_source_ingestion" in ast.unparse(manual_poll)
    assert "apply_async" in source


def test_worker_claims_a_queued_fetch_run() -> None:
    task = _function(TASK_PATH, "ingest_source_task")
    workflow = Path(__file__).parents[1] / "modules/source_ingestion/ingestion_workflow.py"
    workflow_source = workflow.read_text()

    assert "fetch_run_id" in ast.unparse(task)
    assert "fetch_run_id=fetch_run_id" in workflow_source
    assert "FetchRunStatus.QUEUED.value" in workflow_source
