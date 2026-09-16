"""Provider package boundary policy (§15).

Providers may own remote protocol concerns only. Domain decisions must live
outside ``providers/``.
"""

from __future__ import annotations

from pathlib import Path

PROVIDERS_DIR = Path(__file__).resolve().parent

# Imports that must not appear under providers/ (except documented exceptions).
FORBIDDEN_DOMAIN_IMPORT_FRAGMENTS: frozenset[str] = frozenset(
    {
        "chess_intelligence.models",
        "chess_intelligence.dedupe",
        "chess_intelligence.famous",
        "chess_intelligence.content_opportunity",
        "chess_intelligence.content_score",
        "chess_intelligence.fingerprint",
        "chess_intelligence.analysis_",
        "chess_intelligence.catalog_job",
        "chess_video.service",
        "chess_video.models",
        "chess_video.render",
    }
)

# Files allowed to reference ChessParseError for HTTP mapping only.
HTTP_MAPPING_ALLOWLIST: frozenset[str] = frozenset({"http_errors.py"})

PROVIDER_OWNED_CONCERNS: tuple[str, ...] = (
    "remote protocol",
    "authentication",
    "request construction",
    "pagination",
    "timeouts",
    "rate limits",
    "remote DTO parsing",
)

DOMAIN_OWNED_CONCERNS: tuple[str, ...] = (
    "canonical identity",
    "dedupe semantics",
    "famous status",
    "content opportunity",
    "video rendering",
)


def scan_provider_domain_leaks(*, root: Path | None = None) -> list[str]:
    """Return ``path:line:snippet`` hits for forbidden domain imports in providers/."""
    base = root or PROVIDERS_DIR
    hits: list[str] = []
    for path in sorted(base.rglob("*.py")):
        if path.name == "boundary.py":
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for fragment in FORBIDDEN_DOMAIN_IMPORT_FRAGMENTS:
                if fragment in line:
                    hits.append(f"{path.name}:{i}:{stripped[:120]}")
    return hits
