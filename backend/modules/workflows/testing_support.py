"""Dry-run / mock helpers for workflow testing (Phase 15)."""

from __future__ import annotations

from typing import Any

from backend.modules.workflows.nodes.base import NodeResult, NodeResultStatus

GENERATION_NODE_TYPES = frozenset(
    {
        "generate_text",
        "generate_canonical_content",
        "summarize",
        "generate_script",
        "fact_review",
        "generate_image",
        "generate_video",
        "generate_tts",
        "generate_chess_video",
        "generate_chess_narrative",
    }
)


def testing_flags(
    *,
    dry_run: bool = False,
    mock_generation: bool = False,
    simulate_approval: bool = False,
) -> dict[str, Any]:
    return {
        "dry_run": bool(dry_run),
        "mock_generation": bool(mock_generation),
        "simulate_approval": bool(simulate_approval),
    }


def merge_dry_run_config(
    run_config: dict[str, Any] | None,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    merged = dict(run_config or {})
    if dry_run:
        merged["dry_run"] = True
    return merged


def mock_generation_result(node_type: str, inputs: dict[str, Any]) -> NodeResult:
    """Deterministic fake output — no LLM/media providers."""
    if node_type == "summarize":
        text = str(inputs.get("text") or "")[:200]
        output: dict[str, Any] = {
            "text": f"[mock summarize] {text}",
            "provider": "mock",
        }
    elif node_type == "generate_canonical_content":
        plan_id = str(inputs.get("content_plan_id") or "00000000-0000-4000-8000-000000000002")
        output = {
            "content_job_id": "00000000-0000-4000-8000-000000000001",
            "content_plan_id": plan_id,
            "text": f"[mock canonical] plan={plan_id[:36]}",
            "status": "completed",
            "risk_label": "low",
            "asset_group_id": None,
            "target_social_account_ids": [],
            "provider": "mock",
        }
    elif node_type == "fact_review":
        output = {
            "risk_label": "low",
            "blocked": False,
            "fail_closed": False,
            "topic_categories": [],
            "reasons": ["mock"],
            "policy_flags": [],
            "review": {"provider": "mock"},
        }
    elif node_type in {"generate_image", "generate_video", "generate_tts"}:
        output = {
            "asset_url": f"mock://{node_type}",
            "provider": "mock",
            "mocked": True,
        }
    elif node_type == "generate_chess_video":
        output = {
            "chess_video_job_id": "00000000-0000-4000-8000-0000000000c1",
            "status": "completed",
            "video_public_url": "mock://chess-video",
            "thumbnail_public_url": None,
            "render_fingerprint": "mock-fp",
            "provider": "mock",
            "mocked": True,
        }
    elif node_type == "generate_chess_narrative":
        game_id = str(inputs.get("chess_game_id") or "00000000-0000-4000-8000-0000000000c2")
        output = {
            "chess_game_id": game_id,
            "narrative": f"[mock narrative] game={game_id[:36]}",
            "moment_count": len(inputs.get("selected_moments") or []),
            "provider": "mock",
        }
    else:
        prompt = str(inputs.get("prompt") or inputs.get("topic") or "content")
        output = {
            "text": f"[mock {node_type}] {prompt[:240]}",
            "provider": "mock",
        }
    return NodeResult(status=NodeResultStatus.SUCCEEDED, output=output)


def maybe_mock_node_result(
    *,
    node_type: str,
    inputs: dict[str, Any],
    snapshot: dict[str, Any],
) -> NodeResult | None:
    testing = snapshot.get("testing")
    if not isinstance(testing, dict):
        return None
    if not testing.get("mock_generation"):
        return None
    if node_type not in GENERATION_NODE_TYPES:
        return None
    return mock_generation_result(node_type, inputs)


def simulated_approval_result(inputs: dict[str, Any]) -> NodeResult:
    return NodeResult(
        status=NodeResultStatus.SUCCEEDED,
        output={
            "approval_request_id": "00000000-0000-4000-8000-000000000000",
            "status": "approved",
            "channels": ["simulated"],
            "simulated": True,
            "content_job_id": str(inputs.get("content_job_id") or ""),
        },
    )
