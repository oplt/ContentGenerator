"""Phase 26 — chess dependency policy guards."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"

# PyPI names that must not appear in backend lock-style dependency lists.
FORBIDDEN_BACKEND = (
    "stockfish",  # PyPI wrapper pretending to be the engine
    "python-stockfish",
    "stockfish-python",
    "berserk",  # Lichess SDK — use core.http adapters instead
    "chess.com",
    "chesscom",
)

REQUIRED_BACKEND = (
    "chess",
    "httpx",
    "sqlalchemy",
    "pydantic",
    "celery",
    "redis",
    "PyYAML",
    "zstandard",
)

FORBIDDEN_FRONTEND = (
    "chess.js",
    "chessops",
    "react-chessboard",
    "cm-chessboard",
    "@chrisoakman/chessboardjs",
)


def _dep_names(text: str) -> set[str]:
    names: set[str] = set()
    for raw in re.findall(r'["\']?([A-Za-z0-9_.@/-]+)["\']?\s*[><=~!\[]', text):
        names.add(raw.split("[")[0].strip().lower())
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        # requirements style: name>=1
        m = re.match(r"^([A-Za-z0-9_.-]+)", line)
        if m:
            names.add(m.group(1).lower())
    return names


def test_backend_manifests_reuse_allowed_deps() -> None:
    pyproject = (BACKEND / "pyproject.toml").read_text(encoding="utf-8")
    requirements = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
    blob = f"{pyproject}\n{requirements}"
    names = _dep_names(blob)
    for required in REQUIRED_BACKEND:
        assert required.lower() in names, f"missing required chess dep {required}"


def test_backend_forbids_engine_and_provider_sdks() -> None:
    pyproject = (BACKEND / "pyproject.toml").read_text(encoding="utf-8")
    requirements = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
    blob = f"{pyproject}\n{requirements}".lower()
    for forbidden in FORBIDDEN_BACKEND:
        # word-boundary-ish: avoid matching "chess" inside "stockfish"
        pattern = rf"(?m)^[^#\n]*\b{re.escape(forbidden.lower())}\b"
        assert not re.search(pattern, blob), f"forbidden dependency listed: {forbidden}"


def test_stockfish_adapter_uses_external_binary() -> None:
    source = (
        BACKEND / "modules/chess_intelligence/engine/stockfish.py"
    ).read_text(encoding="utf-8")
    assert "popen_uci" in source
    assert "STOCKFISH_PATH" in source or "path" in source
    assert "import stockfish" not in source
    assert "from stockfish" not in source


def test_frontend_avoids_heavy_chess_board_libs() -> None:
    package = (FRONTEND / "package.json").read_text(encoding="utf-8")
    lower = package.lower()
    for forbidden in FORBIDDEN_FRONTEND:
        assert forbidden.lower() not in lower, f"forbidden frontend dep: {forbidden}"
    preview = (
        FRONTEND / "src/features/chess/ChessBoardPreview.tsx"
    ).read_text(encoding="utf-8")
    assert "from \"chess.js\"" not in preview
    assert "from 'chess.js'" not in preview
    assert "no chess.js dependency" in preview.lower()


def test_dependency_policy_doc_exists() -> None:
    path = REPO / "docs/chess-dependency-policy.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "STOCKFISH_PATH" in text
    assert "python-chess" in text or "`chess`" in text
    assert "not" in text.lower() and "python package" in text.lower()
