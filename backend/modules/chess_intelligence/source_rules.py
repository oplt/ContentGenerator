"""Phase 20 — conservative external source rules for chess providers.

Allowed paths: documented APIs, operator-supplied PGN/dataset files, editorial YAML.
Forbidden: automated scrapers of curated proprietary sites (e.g. chessgames.com).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class IntegrationMode(str, Enum):
    DOCUMENTED_API = "documented_api"
    BULK_DATASET = "bulk_dataset"
    PGN_BATCH = "pgn_batch"
    MANUAL = "manual"
    EDITORIAL = "editorial"


@dataclass(frozen=True, slots=True)
class ProviderRule:
    provider: str
    mode: IntegrationMode
    summary: str
    docs_url: str | None = None
    allows_live_http: bool = False
    allows_bulk_file: bool = False


# Stable registry — new live HTTP adapters must be added here intentionally.
PROVIDER_RULES: dict[str, ProviderRule] = {
    "lichess_masters": ProviderRule(
        provider="lichess_masters",
        mode=IntegrationMode.DOCUMENTED_API,
        summary="Lichess Opening Explorer masters API only",
        docs_url="https://lichess.org/api#tag/Opening-Explorer",
        allows_live_http=True,
    ),
    "lichess_puzzles": ProviderRule(
        provider="lichess_puzzles",
        mode=IntegrationMode.DOCUMENTED_API,
        summary="Lichess puzzle API and official puzzle database dump",
        docs_url="https://database.lichess.org/#puzzles",
        allows_live_http=True,
        allows_bulk_file=True,
    ),
    "lichess": ProviderRule(
        provider="lichess",
        mode=IntegrationMode.DOCUMENTED_API,
        summary="Lichess public API (generic label)",
        docs_url="https://lichess.org/api",
        allows_live_http=True,
    ),
    "chesscom": ProviderRule(
        provider="chesscom",
        mode=IntegrationMode.DOCUMENTED_API,
        summary="Chess.com Published Data API only",
        docs_url="https://www.chess.com/news/view/published-data-api",
        allows_live_http=True,
    ),
    "pgn_archive": ProviderRule(
        provider="pgn_archive",
        mode=IntegrationMode.PGN_BATCH,
        summary="Operator-supplied downloadable PGN archive (local file import)",
        allows_bulk_file=True,
    ),
    "pgn_mentor": ProviderRule(
        provider="pgn_mentor",
        mode=IntegrationMode.PGN_BATCH,
        summary="Operator-supplied PGN Mentor-style archive label",
        allows_bulk_file=True,
    ),
    "manual": ProviderRule(
        provider="manual",
        mode=IntegrationMode.MANUAL,
        summary="Operator-pasted PGN via catalog API",
    ),
    "api_import": ProviderRule(
        provider="api_import",
        mode=IntegrationMode.MANUAL,
        summary="Catalog API import path",
    ),
    "famous_catalog": ProviderRule(
        provider="famous_catalog",
        mode=IntegrationMode.EDITORIAL,
        summary="SignalForge-owned famous-game YAML (not scraped annotations)",
    ),
}

# Do not add HTTP adapters that scrape these hosts.
FORBIDDEN_SCRAPE_HOSTS: frozenset[str] = frozenset(
    {
        "chessgames.com",
        "www.chessgames.com",
        "chess-db.com",
        "www.chess-db.com",
    }
)

FORBIDDEN_PROVIDER_TOKENS: frozenset[str] = frozenset(
    {
        "chessgames",
        "chess_games",
        "scraper",
        "scraped",
        "crawl",
        "crawler",
    }
)


class ChessSourceRuleError(ValueError):
    """Raised when an ingest path violates Phase 20 source rules."""


def normalize_provider(provider: str | None) -> str:
    return (provider or "").strip().lower()


def get_provider_rule(provider: str | None) -> ProviderRule | None:
    return PROVIDER_RULES.get(normalize_provider(provider))


def _looks_forbidden_provider(provider: str) -> bool:
    tokens = {t for t in provider.replace("-", "_").split("_") if t}
    if tokens & FORBIDDEN_PROVIDER_TOKENS:
        return True
    compact = provider.replace("_", "").replace("-", "")
    return any(tok.replace("_", "") in compact for tok in ("chessgames", "scraper", "crawler"))


def assert_provider_allowed_for_ingest(provider: str | None) -> str:
    """Return normalized provider id or raise if scrape/forbidden labels are used."""
    normalized = normalize_provider(provider) or "manual"
    if _looks_forbidden_provider(normalized):
        raise ChessSourceRuleError(
            f"Provider '{normalized}' is not allowed — curated-site scrapers are forbidden "
            "(use documented APIs, local PGN/dataset files, or SignalForge famous-game YAML)."
        )
    rule = PROVIDER_RULES.get(normalized)
    if rule is not None:
        return normalized
    # Custom archive labels (e.g. twic_1520) are OK as PGN batch tags.
    if normalized.startswith(("pgn_", "archive_", "twic_", "local_")):
        return normalized
    raise ChessSourceRuleError(
        f"Unknown chess provider '{normalized}'. Use a documented provider "
        f"({', '.join(sorted(PROVIDER_RULES))}) or a pgn_/archive_/twic_/local_ batch label."
    )


def assert_bulk_file_allowed(provider: str | None) -> str:
    normalized = assert_provider_allowed_for_ingest(provider)
    rule = PROVIDER_RULES.get(normalized)
    if rule is not None and not rule.allows_bulk_file and rule.mode not in {
        IntegrationMode.PGN_BATCH,
        IntegrationMode.BULK_DATASET,
        IntegrationMode.MANUAL,
    }:
        raise ChessSourceRuleError(
            f"Provider '{normalized}' does not allow bulk file ingest "
            f"(mode={rule.mode.value})."
        )
    if rule is not None and rule.mode == IntegrationMode.DOCUMENTED_API and not rule.allows_bulk_file:
        raise ChessSourceRuleError(
            f"Provider '{normalized}' is live-API only — do not treat HTML scrape dumps as input."
        )
    return normalized


def assert_live_http_allowed(provider: str | None) -> str:
    normalized = assert_provider_allowed_for_ingest(provider)
    rule = PROVIDER_RULES.get(normalized)
    if rule is None or not rule.allows_live_http:
        raise ChessSourceRuleError(
            f"Provider '{normalized}' has no approved live HTTP adapter."
        )
    return normalized


def host_from_url(url: str | None) -> str | None:
    if not url or not str(url).strip():
        return None
    try:
        host = (urlparse(str(url).strip()).hostname or "").lower()
    except Exception:  # noqa: BLE001 — defensive parse
        return None
    return host or None


def assert_url_not_scrape_target(url: str | None, *, for_automated_fetch: bool) -> None:
    """Block automated fetch against forbidden curated hosts.

    Editorial research links may still be stored when ``for_automated_fetch`` is False.
    """
    if not for_automated_fetch:
        return
    host = host_from_url(url)
    if host and host in FORBIDDEN_SCRAPE_HOSTS:
        raise ChessSourceRuleError(
            f"Automated fetch from '{host}' is forbidden. "
            "Use documented APIs or operator-supplied files; keep SignalForge famous-game metadata."
        )


def live_http_providers() -> frozenset[str]:
    return frozenset(p for p, r in PROVIDER_RULES.items() if r.allows_live_http)
