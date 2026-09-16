"""Transaction ownership: routers/repos flush-only; services allowlisted commits."""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MODULES = BACKEND_ROOT / "modules"

# Split-phase / auth session durability — explicit mid-workflow commits only.
SERVICE_COMMIT_ALLOWLIST: frozenset[str] = frozenset(
    {
        "modules/publishing/job_executor.py",
        "modules/publishing/publish_orchestration.py",
        "modules/content_generation/workflow.py",
        "modules/content_generation/asset_persistence.py",
        "modules/approvals/telegram_callbacks.py",
        "modules/approvals/telegram_messages.py",
        "modules/approvals/webhook_processing.py",
        "modules/workflows/webhook_ingress.py",
        "modules/identity_access/auth_credentials.py",
        "modules/identity_access/auth_sessions.py",
        "modules/chess_video/service.py",
    }
)

ROUTER_COMMIT_ALLOWLIST: set[tuple[str, str]] = {
    ("modules/chess_video/router.py", "create_chess_video"),
    ("modules/chess_video/router.py", "retry_chess_video"),
    ("modules/chess_video/router.py", "delete_chess_video"),
    ("modules/source_ingestion/router.py", "_enqueue_source_ingestion"),
}


def _relative(path: Path) -> str:
    return path.relative_to(BACKEND_ROOT).as_posix()


def _calls_commit(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commit"
        for node in ast.walk(tree)
    )


def test_request_routers_do_not_commit_transactions() -> None:
    violations: list[str] = []
    for router_path in MODULES.glob("*/router.py"):
        if "_dormant" in router_path.parts:
            continue
        relative_path = _relative(router_path)
        tree = ast.parse(router_path.read_text(), filename=str(router_path))
        for function in (node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)):
            key = (relative_path, function.name)
            if key in ROUTER_COMMIT_ALLOWLIST:
                continue
            if _calls_commit(function):
                violations.append(f"{relative_path}:{function.lineno} ({function.name})")
    assert not violations, "Request routers must leave commits to get_db:\n" + "\n".join(violations)


def test_repositories_do_not_commit() -> None:
    violations: list[str] = []
    for path in MODULES.rglob("*.py"):
        if "_dormant" in path.parts:
            continue
        name = path.name
        if not (name == "repository.py" or name.startswith("repository_")):
            continue
        relative = _relative(path)
        tree = ast.parse(path.read_text(), filename=str(path))
        if _calls_commit(tree):
            violations.append(relative)
    assert not violations, "Repositories must flush only:\n" + "\n".join(violations)


def test_services_only_commit_when_allowlisted() -> None:
    violations: list[str] = []
    for path in MODULES.rglob("*.py"):
        if "_dormant" in path.parts:
            continue
        relative = _relative(path)
        if relative in SERVICE_COMMIT_ALLOWLIST:
            continue
        # Skip routers (covered separately) and pure schema/model modules.
        if path.name in {"router.py", "models.py", "schemas.py", "providers.py"}:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        if _calls_commit(tree):
            violations.append(relative)
    assert not violations, (
        "Unexpected service/module commit(); add to allowlist only for split-phase "
        "durability:\n" + "\n".join(violations)
    )
