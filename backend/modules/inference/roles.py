"""
Multi-role LLM inference pipeline.

Each role is a pure async function that takes a context dict and returns
a typed Pydantic model. Roles are stateless and composable — the orchestrator
wires them together in sequence.
"""
from __future__ import annotations

from backend.modules.inference.role_runners import (
    run_extractor,
    run_optimizer,
    run_planner,
    run_reviewer,
    run_scorer,
    run_writer,
)
from backend.modules.inference.roles_parse import _parse_json_output, parse_json_output

__all__ = [
    "_parse_json_output",
    "parse_json_output",
    "run_extractor",
    "run_optimizer",
    "run_planner",
    "run_reviewer",
    "run_scorer",
    "run_writer",
]
