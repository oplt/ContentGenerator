"""Phase 8: dashboard list endpoints avoid per-row database queries."""

import ast
from pathlib import Path


CONTENT_ROUTER = Path(__file__).parents[1] / "modules/content_generation/router.py"
CONTENT_SERVICE = Path(__file__).parents[1] / "modules/content_generation/service.py"
PUBLISHING_REPOSITORY = Path(__file__).parents[1] / "modules/publishing/repository.py"


def _function(path: Path, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    tree = ast.parse(path.read_text())
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name
    )


def test_content_jobs_list_uses_batch_detail_assembly() -> None:
    route = ast.unparse(_function(CONTENT_ROUTER, "list_content_jobs"))
    service = ast.unparse(_function(CONTENT_SERVICE, "list_job_details"))

    assert "list_job_details" in route
    assert "get_job_detail" not in route
    assert "list_assets_for_jobs" in service
    assert "list_asset_groups_for_jobs" in service


def test_published_post_account_filter_is_sql_side() -> None:
    repository = ast.unparse(_function(PUBLISHING_REPOSITORY, "list_published_posts"))

    assert "social_account_id" in repository
    assert "statement = statement.where" in repository
