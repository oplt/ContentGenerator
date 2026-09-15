"""Unit tests for ObjectStorage.upload_file."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.core.storage import ObjectStorage, ObjectStorageError, StorageNotConfiguredError


def test_upload_file_streams_via_boto_upload_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.core.storage.settings.STORAGE_BUCKET", "sf-bucket")
    monkeypatch.setattr("backend.core.storage.settings.STORAGE_PUBLIC_BASE_URL", "http://minio/sf-bucket")
    monkeypatch.setattr("backend.core.storage.settings.STORAGE_BACKEND", "s3")

    source = tmp_path / "video.mp4"
    source.write_bytes(b"fake-mp4-bytes")

    storage = ObjectStorage()
    client = MagicMock()

    async def _run() -> str:
        with patch.object(ObjectStorage, "_client", new=client):
            return await storage.upload_file(
                object_key="tenant/a/chess/out.mp4",
                file_path=source,
                content_type="video/mp4",
            )

    url = asyncio.run(_run())
    client.upload_file.assert_called_once_with(
        Filename=str(source),
        Bucket="sf-bucket",
        Key="tenant/a/chess/out.mp4",
        ExtraArgs={"ContentType": "video/mp4"},
    )
    assert url == "http://minio/sf-bucket/tenant/a/chess/out.mp4"


def test_upload_file_local_backend_copies_to_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "store"
    monkeypatch.setattr("backend.core.storage.settings.STORAGE_BACKEND", "local")
    monkeypatch.setattr("backend.core.storage.settings.STORAGE_LOCAL_ROOT", str(root))
    monkeypatch.setattr("backend.core.storage.settings.STORAGE_PUBLIC_BASE_URL", "")
    monkeypatch.setattr("backend.core.storage.settings.API_V1_PREFIX", "/api/v1")

    source = tmp_path / "video.mp4"
    source.write_bytes(b"fake-mp4-bytes")
    storage = ObjectStorage()

    url = asyncio.run(
        storage.upload_file(
            object_key="tenants/t/chess/out.mp4",
            file_path=source,
            content_type="video/mp4",
        )
    )
    assert url == "/api/v1/media/tenants/t/chess/out.mp4"
    assert (root / "tenants/t/chess/out.mp4").read_bytes() == b"fake-mp4-bytes"


def test_local_public_url_ignores_minio_default_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.core.storage.settings.STORAGE_BACKEND", "local")
    monkeypatch.setattr("backend.core.storage.settings.STORAGE_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "backend.core.storage.settings.STORAGE_PUBLIC_BASE_URL",
        "http://localhost:9000/content-generator",
    )
    monkeypatch.setattr("backend.core.storage.settings.API_V1_PREFIX", "/api/v1")
    storage = ObjectStorage()
    assert storage.public_url_for("a/b.mp4") == "/api/v1/media/a/b.mp4"


def test_resolve_local_path_rejects_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.core.storage.settings.STORAGE_BACKEND", "local")
    monkeypatch.setattr("backend.core.storage.settings.STORAGE_LOCAL_ROOT", str(tmp_path))
    storage = ObjectStorage()
    with pytest.raises(ObjectStorageError, match="Invalid object key"):
        storage.resolve_local_path("../secret")


def test_delete_prefix_removes_local_job_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.core.storage.settings.STORAGE_BACKEND", "local")
    monkeypatch.setattr("backend.core.storage.settings.STORAGE_LOCAL_ROOT", str(tmp_path))
    job_dir = tmp_path / "tenants" / "t" / "chess-videos" / "job-1"
    job_dir.mkdir(parents=True)
    (job_dir / "video.mp4").write_bytes(b"mp4")
    (job_dir / "thumbnail.png").write_bytes(b"png")
    storage = ObjectStorage()
    asyncio.run(storage.delete_prefix(prefix="tenants/t/chess-videos/job-1"))
    assert not job_dir.exists()


def test_upload_file_requires_existing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.core.storage.settings.STORAGE_BUCKET", "sf-bucket")
    storage = ObjectStorage()

    async def _run() -> None:
        await storage.upload_file(
            object_key="x.mp4",
            file_path=tmp_path / "missing.mp4",
            content_type="video/mp4",
        )

    with pytest.raises(ObjectStorageError, match="not found"):
        asyncio.run(_run())


def test_upload_file_requires_configured_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.core.storage.settings.STORAGE_BACKEND", "s3")
    monkeypatch.setattr("backend.core.storage.settings.STORAGE_BUCKET", "")
    source = tmp_path / "video.mp4"
    source.write_bytes(b"x")
    storage = ObjectStorage()

    async def _run() -> None:
        await storage.upload_file(object_key="x.mp4", file_path=source, content_type="video/mp4")

    with pytest.raises(StorageNotConfiguredError):
        asyncio.run(_run())
