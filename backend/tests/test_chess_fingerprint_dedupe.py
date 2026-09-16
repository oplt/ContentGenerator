"""§17 — single fingerprint + ChessGameDedupeService layer; no provider-local dedupe."""

from __future__ import annotations

import ast
from pathlib import Path

from backend.modules.chess_intelligence.fingerprint import (
    compute_game_fingerprint,
    fingerprint_from_parsed,
)
from backend.modules.chess_intelligence.normalizer import chess_game_from_parsed
from backend.modules.chess_intelligence.providers.boundary import scan_provider_domain_leaks
from backend.modules.chess_video.parser import parse_chess_input

_BASE_PGN = """
[Event "A"]
[White "Kasparov"]
[Black "Karpov"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 1-0
"""

# Harmless presentation differences — same actual game.
_COMMENT_PGN = """
[Event "A"]
[White "Kasparov"]
[Black "Karpov"]
[Result "1-0"]

1. e4 {opening} e5 2. Nf3 Nc6 1-0
"""

_HEADER_REORDER_PGN = """
[Black "Karpov"]
[White "Kasparov"]
[Result "1-0"]
[Event "A"]

1. e4 e5 2. Nf3 Nc6 1-0
"""

_FORMAT_PGN = """
[Event "A"]
[White "Kasparov"]
[Black "Karpov"]
[Result "1-0"]

1.e4 e5  2.Nf3   Nc6 1-0
"""

_ANNOTATION_PGN = """
[Event "A"]
[White "Kasparov"]
[Black "Karpov"]
[Result "1-0"]

1. e4 e5 2. Nf3!! Nc6 1-0
"""

_NAG_PGN = """
[Event "A"]
[White "Kasparov"]
[Black "Karpov"]
[Result "1-0"]

1. e4 e5 2. Nf3 $1 Nc6 1-0
"""

# Domain modules allowed to persist/upsert games via ChessGameDedupeService.
_GAME_INGRESS_MODULES = (
    "backend/modules/chess_intelligence/dedupe.py",
    "backend/modules/chess_intelligence/service.py",
    "backend/modules/chess_intelligence/importers/pgn_archive.py",
    "backend/modules/chess_intelligence/catalog_job_sync.py",
)


def test_fingerprint_stable_despite_harmless_pgn_differences() -> None:
    fps = {
        label: fingerprint_from_parsed(parse_chess_input(pgn, "pgn"))
        for label, pgn in (
            ("base", _BASE_PGN),
            ("comments", _COMMENT_PGN),
            ("header_order", _HEADER_REORDER_PGN),
            ("formatting", _FORMAT_PGN),
            ("annotations", _ANNOTATION_PGN),
            ("nags", _NAG_PGN),
        )
    }
    assert len(set(fps.values())) == 1, fps


def test_fingerprint_uses_starting_fen_and_uci_not_provider_ids() -> None:
    import uuid

    parsed = parse_chess_input(_BASE_PGN, "pgn")
    a = chess_game_from_parsed(
        tenant_id=uuid.uuid4(),
        parsed=parsed,
        source_provider="lichess_masters",
        source_external_id="abc-111",
    )
    b = chess_game_from_parsed(
        tenant_id=uuid.uuid4(),
        parsed=parsed,
        source_provider="chesscom",
        source_external_id="zzz-999",
    )
    assert a.game_fingerprint == b.game_fingerprint
    assert a.game_fingerprint == fingerprint_from_parsed(parsed)
    # Provider ids live on provenance fields only.
    assert a.source_external_id != b.source_external_id
    assert a.game_fingerprint != a.source_external_id


def test_fingerprint_sensitive_to_move_sequence() -> None:
    start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    a = compute_game_fingerprint(
        starting_fen=start, uci_moves=["e2e4", "e7e5"], result="1-0"
    )
    b = compute_game_fingerprint(
        starting_fen=start, uci_moves=["e2e4", "c7c5"], result="1-0"
    )
    assert a != b


def test_providers_do_not_import_fingerprint_or_dedupe() -> None:
    assert scan_provider_domain_leaks() == []


def test_game_ingress_converges_on_dedupe_service() -> None:
    """Catalog write paths must call ChessGameDedupeService — not ad-hoc inserts."""
    root = Path(__file__).resolve().parents[2]
    for rel in _GAME_INGRESS_MODULES:
        if rel.endswith("dedupe.py"):
            continue
        path = root / rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.endswith(".dedupe") or node.module == "dedupe":
                    for alias in node.names:
                        names.add(alias.name)
            if isinstance(node, ast.Name):
                names.add(node.id)
            if isinstance(node, ast.Attribute):
                names.add(node.attr)
        assert "ChessGameDedupeService" in names, f"{rel} must use ChessGameDedupeService"
        assert "upsert_game" in names, f"{rel} must call upsert_game"
