"""§34 — security + external-service rules for chess ingest.

Credentials stay backend-only. Respect provider terms, rate limits, licensing,
attribution, and ``source_rules``. Never scrape proprietary commentary.
Factual catalog rows ≠ SignalForge editorial narrative.
Famous YAML is SignalForge-owned metadata — not third-party annotations.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.modules.chess_intelligence.famous_catalog import FamousGameEntry
from backend.modules.chess_intelligence.source_rules import (
    FORBIDDEN_SCRAPE_HOSTS,
    PROVIDER_RULES,
)


@dataclass(frozen=True, slots=True)
class SecurityRule:
    rule: str
    enforcement: str


SECURITY_RULES: tuple[SecurityRule, ...] = (
    SecurityRule(
        "provider_credentials_backend_only",
        "LICHESS_API_TOKEN / rate limits / STOCKFISH_PATH in backend Settings; never Vite",
    ),
    SecurityRule(
        "respect_provider_terms_and_rate_limits",
        "Documented APIs only; LICHESS_/CHESSCOM_RATE_LIMIT_RPH + core.http concurrency",
    ),
    SecurityRule(
        "licensing_and_source_attribution",
        "licenses.py → license_note on games/puzzles/sources; provenance panel",
    ),
    SecurityRule(
        "source_rules_and_forbidden_scrapers",
        "source_rules.PROVIDER_RULES + FORBIDDEN_SCRAPE_HOSTS / provider tokens",
    ),
    SecurityRule(
        "no_proprietary_commentary_scrape",
        "No HTML scrapers; famous_games.yaml is SignalForge editorial only",
    ),
    SecurityRule(
        "factual_catalog_vs_editorial_narrative",
        "ChessGame/ChessPuzzle + provenance are facts; briefs/publish stay separate",
    ),
    SecurityRule(
        "no_silent_third_party_annotations_in_famous",
        "FamousGameEntry forbids annotation/commentary/pgn dump fields",
    ),
)

# Famous catalog may carry matching/editorial metadata only — not scraped notes.
FAMOUS_ALLOWED_FIELDS: frozenset[str] = frozenset(FamousGameEntry.model_fields)
FAMOUS_FORBIDDEN_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "annotation",
        "annotations",
        "commentary",
        "comments",
        "pgn",
        "normalized_pgn",
        "moves",
        "analysis",
        "engine_lines",
        "scraped_notes",
    }
)

BACKEND_ONLY_SECRET_NAMES: frozenset[str] = frozenset(
    {
        "LICHESS_API_TOKEN",
        "STOCKFISH_PATH",
    }
)


def credentials_must_stay_backend_only() -> bool:
    return True


def famous_entry_fields_are_safe() -> bool:
    return FAMOUS_ALLOWED_FIELDS.isdisjoint(FAMOUS_FORBIDDEN_FIELD_NAMES)


def documented_live_providers() -> tuple[str, ...]:
    return tuple(
        sorted(
            name
            for name, rule in PROVIDER_RULES.items()
            if rule.allows_live_http
        )
    )


def forbidden_scrape_hosts() -> frozenset[str]:
    return FORBIDDEN_SCRAPE_HOSTS
