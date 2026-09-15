"""JSON parsing helpers for multi-role inference."""
from __future__ import annotations

import json
import re


def parse_json_output(raw: str, default: dict) -> dict:
    """Strip markdown fences and parse JSON; return default on failure."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except (json.JSONDecodeError, ValueError):
                pass
    return default


# Back-compat alias
_parse_json_output = parse_json_output
