"""§4 — archive import manifest embeds into catalog jobs (no new table)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from backend.modules.chess_intelligence.import_manifest import (
    ArchiveImportManifest,
    attach_manifest_to_result,
    build_archive_manifest,
    sha256_file,
)


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "archive.pgn"
    payload = b"[Event \"X\"]\n\n1. e4 e5 1-0\n"
    path.write_bytes(payload)
    digest, size = sha256_file(path)
    assert size == len(payload)
    assert digest == hashlib.sha256(payload).hexdigest()


def test_build_archive_manifest_fields(tmp_path: Path) -> None:
    path = tmp_path / "wch.pgn"
    path.write_text("1. e4 e5 1-0\n", encoding="utf-8")
    manifest = build_archive_manifest(
        path=path,
        provider="pgn_mentor",
        source_name="world_championship",
        import_batch_id="batch-1",
        archive_version="2026.09",
        source_uri="https://example.test/wch.pgn",
    )
    assert manifest.archive_id == "world_championship"
    assert manifest.provider == "pgn_mentor"
    assert manifest.checksum_sha256
    assert manifest.size_bytes > 0
    assert manifest.source_uri == "https://example.test/wch.pgn"
    assert manifest.archive_version == "2026.09"
    assert manifest.import_batch_id == "batch-1"
    assert manifest.metadata["archive_file"] == "wch.pgn"


def test_attach_manifest_aliases_counts() -> None:
    manifest = ArchiveImportManifest(
        archive_id="a",
        provider="pgn_archive",
        source_uri="file:///tmp/a.pgn",
        checksum_sha256="abc",
        size_bytes=10,
        archive_version=None,
        retrieved_at="2026-09-16T00:00:00+00:00",
        import_batch_id="b1",
        metadata={},
    )
    out = attach_manifest_to_result(
        {
            "scanned": 10,
            "inserted": 2,
            "linked_source": 1,
            "skipped_duplicate": 7,
            "skipped_error": 0,
        },
        manifest,
        import_started_at="t0",
        import_completed_at="t1",
    )
    assert out["archive_manifest"]["checksum_sha256"] == "abc"
    assert out["game_count"] == 10
    assert out["new_game_count"] == 2
    assert out["existing_game_count"] == 8
    assert out["failure_count"] == 0
    assert out["import_started_at"] == "t0"
    assert out["import_completed_at"] == "t1"


def test_no_separate_manifest_table_in_models() -> None:
    """Decision: reuse ChessCatalogJob JSON — do not add ChessArchiveImportManifest ORM."""
    from backend.modules.chess_intelligence import catalog_job_models as job_models
    from backend.modules.chess_intelligence import models as chess_models

    names = {name for name in dir(chess_models) + dir(job_models) if name.startswith("Chess")}
    assert "ChessArchiveImportManifest" not in names
    assert "ChessImportManifest" not in names
