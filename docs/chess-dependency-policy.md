# Chess dependency policy (Phase 26)

Reuse the platform stack. Add packages only with a concrete chess need.

## Allowed (reuse)

| Capability | Dependency | Notes |
|------------|------------|-------|
| Rules / PGN / SAN / UCI | `chess` (python-chess) | Authoritative move legality + puzzle solution validation |
| HTTP providers | `httpx` via `backend.core.http` | Shared client, retries, budgets — no per-provider SDK |
| Persistence | SQLAlchemy + PostgreSQL + Alembic | Catalog / analysis / catalog jobs |
| API contracts | Pydantic | DTOs + request/response schemas |
| Async work | Celery + Redis | Analysis + catalog import jobs |
| Famous catalog YAML | `PyYAML` | `data/famous_games.yaml` |
| Puzzle `.csv.zst` | `zstandard` | Official Lichess dump streaming |
| Video frames | `Pillow` (+ FFmpeg external) | `chess_video` render path |
| Frontend data | TanStack React Query | Catalog hooks |
| Frontend UI | Existing design-system components | No new UI kit |

## External (not PyPI)

| Binary | Config | Role |
|--------|--------|------|
| **Stockfish** | `STOCKFISH_PATH` | Real UCI engine via `chess.engine.SimpleEngine.popen_uci` |
| FFmpeg | existing video pipeline | Encode chess videos |

Stockfish must **not** be installed as a Python package that pretends to be the engine (`stockfish`, `python-stockfish`, etc.). The adapter lives in `modules/chess_intelligence/engine/stockfish.py`.

## Forbidden / avoid

- Provider SDKs that bypass `core.http` rate limits and error mapping
- HTML scrapers / unofficial chess site clients (see source rules)
- Frontend `chess.js` / `react-chessboard` unless a product need exceeds the FEN preview (current preview is dependency-free)
- Bundling Stockfish binaries into the Python wheel or container as a fake “library”

## Justification bar for new deps

1. Cannot be done with an allowed dependency above.
2. License compatible with SignalForge distribution.
3. Documented here + reflected in both `backend/pyproject.toml` and `backend/requirements.txt`.
4. Guarded by `tests/test_chess_dependency_policy.py`.

## Frontend note

`ChessBoardPreview` intentionally avoids chess.js — FEN rendering is local. Prefer that until interactive board editing requires a dedicated library.
