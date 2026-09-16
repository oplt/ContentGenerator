"""§34 — credentials, source rules, famous catalog safety."""

from __future__ import annotations

from pathlib import Path

from backend.modules.chess_intelligence.external_service_security import (
    BACKEND_ONLY_SECRET_NAMES,
    FAMOUS_ALLOWED_FIELDS,
    FAMOUS_FORBIDDEN_FIELD_NAMES,
    SECURITY_RULES,
    credentials_must_stay_backend_only,
    documented_live_providers,
    famous_entry_fields_are_safe,
    forbidden_scrape_hosts,
)
from backend.modules.chess_intelligence.famous_catalog import FamousGameEntry, load_famous_catalog
from backend.modules.chess_intelligence.licenses import PROVIDER_LICENSE_NOTES, license_for_provider
from backend.modules.chess_intelligence.source_rules import FORBIDDEN_SCRAPE_HOSTS

REPO = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO / "frontend" / "src"


def test_security_rules_contract() -> None:
    assert credentials_must_stay_backend_only() is True
    rules = {r.rule for r in SECURITY_RULES}
    assert "provider_credentials_backend_only" in rules
    assert "no_proprietary_commentary_scrape" in rules
    assert "no_silent_third_party_annotations_in_famous" in rules
    assert "factual_catalog_vs_editorial_narrative" in rules
    assert BACKEND_ONLY_SECRET_NAMES >= {"LICHESS_API_TOKEN", "STOCKFISH_PATH"}


def test_famous_entry_schema_excludes_annotation_dumps() -> None:
    assert famous_entry_fields_are_safe() is True
    assert FAMOUS_ALLOWED_FIELDS.isdisjoint(FAMOUS_FORBIDDEN_FIELD_NAMES)
    # Runtime model must not grow forbidden keys silently.
    assert set(FamousGameEntry.model_fields).isdisjoint(FAMOUS_FORBIDDEN_FIELD_NAMES)


def test_famous_yaml_has_no_annotation_keys() -> None:
    catalog = load_famous_catalog()
    assert len(catalog) >= 1
    # Entries already validated by pydantic — also reject raw forbidden keys in YAML text.
    text = (
        REPO / "backend/modules/chess_intelligence/data/famous_games.yaml"
    ).read_text(encoding="utf-8").lower()
    for bad in ("annotation:", "commentary:", "scraped_notes:", "normalized_pgn:"):
        assert bad not in text


def test_licenses_cover_live_providers() -> None:
    for provider in documented_live_providers():
        note = license_for_provider(provider)
        assert note, f"missing license note for {provider}"
        assert provider in PROVIDER_LICENSE_NOTES or provider.startswith("lichess")


def test_forbidden_scrape_hosts_include_curated_sites() -> None:
    hosts = forbidden_scrape_hosts()
    assert hosts is FORBIDDEN_SCRAPE_HOSTS
    assert "chessgames.com" in hosts or "www.chessgames.com" in hosts


def test_frontend_src_has_no_backend_secret_env_names() -> None:
    hits: list[str] = []
    for path in FRONTEND_SRC.rglob("*"):
        if not path.is_file() or path.suffix not in {".ts", ".tsx", ".js", ".jsx", ".env"}:
            continue
        # Contract/docs files may name secrets as forbid lists.
        if path.name in {
            "frontendSeparation.ts",
            "section31Coverage.test.ts",
            "structure.test.ts",
        }:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for secret in BACKEND_ONLY_SECRET_NAMES:
            if secret in text:
                hits.append(f"{path.relative_to(REPO)}:{secret}")
    assert hits == [], f"frontend must not reference backend secrets: {hits}"
