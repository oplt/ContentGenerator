from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StructuredGenerationResult:
    data: dict[str, Any]
    parsed: bool
    raw: str = ""


def _parse_json_object(raw: str, default: dict[str, Any] | None = None) -> StructuredGenerationResult:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])

    # First try: extract first JSON object via regex (handles prose-wrapped output)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    candidate = match.group(0) if match else cleaned
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return StructuredGenerationResult(data=parsed, parsed=True, raw=raw)
    except json.JSONDecodeError:
        pass

    # Second try: parse the full cleaned string as-is (handles model-returned arrays or
    # cases where the regex candidate was broken by multiple top-level objects)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return StructuredGenerationResult(data=parsed, parsed=True, raw=raw)
    except json.JSONDecodeError:
        pass

    return StructuredGenerationResult(data=default or {}, parsed=False, raw=raw)
