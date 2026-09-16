"""Archive import reproducibility — reuse catalog jobs; no extra manifest table.

Audit (§4):

| Need | Already present |
|------|-----------------|
| archive/source id | ``source_name`` + ``archive_file`` on ``ChessGameSource`` |
| provider | job params + source.provider |
| import batch | ``ChessCatalogJob.import_batch_id`` / source.import_batch_id |
| counts | job ``result`` (scanned/inserted/linked/dupes/errors) |
| started/completed | job ``created_at`` / ``updated_at`` (+ status) |
| per-game provenance | ``ChessGameSource.source_metadata`` |

Gap closed here (still **no new table**): stream file checksum + size into job
``params``/``result`` and source metadata so operators can detect archive drift.

Large original archives stay on disk / object storage — Postgres holds normalized
games + this lightweight digest, not raw archive blobs.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ArchiveImportManifest:
    """Lightweight reproducibility record embedded in catalog job JSON."""

    archive_id: str
    provider: str
    source_uri: str | None
    checksum_sha256: str
    size_bytes: int
    archive_version: str | None
    retrieved_at: str
    import_batch_id: str | None
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> tuple[str, int]:
    """Stream SHA-256 + byte size (never load whole archive into RAM)."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def build_archive_manifest(
    *,
    path: Path,
    provider: str,
    source_name: str,
    import_batch_id: str | None = None,
    source_uri: str | None = None,
    archive_version: str | None = None,
    metadata: dict[str, Any] | None = None,
    retrieved_at: datetime | None = None,
) -> ArchiveImportManifest:
    """Compute checksum and assemble manifest for an on-disk archive."""
    checksum, size = sha256_file(path)
    resolved = path.resolve()
    when = (retrieved_at or datetime.now(timezone.utc)).isoformat()
    return ArchiveImportManifest(
        archive_id=source_name or resolved.name,
        provider=provider,
        source_uri=source_uri or resolved.as_uri(),
        checksum_sha256=checksum,
        size_bytes=size,
        archive_version=archive_version,
        retrieved_at=when,
        import_batch_id=import_batch_id,
        metadata={
            "archive_file": resolved.name,
            "file_path": str(resolved),
            **dict(metadata or {}),
        },
    )


def attach_manifest_to_result(
    result: dict[str, Any],
    manifest: ArchiveImportManifest,
    *,
    import_started_at: str | None = None,
    import_completed_at: str | None = None,
) -> dict[str, Any]:
    """Merge counts already on ``result`` with archive digest fields."""
    out = dict(result)
    out["archive_manifest"] = manifest.as_dict()
    if import_started_at:
        out["import_started_at"] = import_started_at
    if import_completed_at:
        out["import_completed_at"] = import_completed_at
    # Prompt-shaped aliases for operators / audits.
    out.setdefault("game_count", out.get("scanned"))
    out.setdefault("new_game_count", out.get("inserted"))
    out.setdefault(
        "existing_game_count",
        (out.get("linked_source") or 0) + (out.get("skipped_duplicate") or 0),
    )
    out.setdefault("failure_count", out.get("skipped_error"))
    return out


def manifest_source_metadata(manifest: ArchiveImportManifest) -> dict[str, Any]:
    """Fields stamped onto each ``ChessGameSource.source_metadata`` row."""
    return {
        "archive_sha256": manifest.checksum_sha256,
        "archive_bytes": manifest.size_bytes,
        "archive_id": manifest.archive_id,
        "archive_uri": manifest.source_uri,
        "archive_version": manifest.archive_version,
    }
