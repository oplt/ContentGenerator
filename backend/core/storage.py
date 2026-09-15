from __future__ import annotations

import asyncio
import logging
import shutil
from functools import cached_property
from pathlib import Path
from typing import Any, cast

from backend.core.config import settings

logger = logging.getLogger(__name__)


class StorageNotConfiguredError(RuntimeError):
    pass


class ObjectStorageError(RuntimeError):
    pass


def _default_local_root() -> Path:
    return Path(__file__).resolve().parents[1] / ".data" / "object-storage"


class ObjectStorage:
    @property
    def is_configured(self) -> bool:
        if self._uses_local:
            return True
        return bool(settings.STORAGE_BUCKET)

    @property
    def _uses_local(self) -> bool:
        return settings.STORAGE_BACKEND.strip().lower() == "local"

    @property
    def local_root(self) -> Path:
        raw = (settings.STORAGE_LOCAL_ROOT or "").strip()
        return Path(raw).expanduser() if raw else _default_local_root()

    @cached_property
    def _client(self) -> Any:
        try:
            import boto3  # type: ignore[import-untyped]
            from botocore.client import Config  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ObjectStorageError(
                "Object storage dependencies are not installed. Run `uv sync` in `backend/`."
            ) from exc

        session = boto3.session.Session()
        return session.client(
            "s3",
            region_name=settings.STORAGE_REGION,
            endpoint_url=settings.STORAGE_ENDPOINT_URL or None,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY or None,
            aws_secret_access_key=settings.STORAGE_SECRET_KEY or None,
            use_ssl=settings.STORAGE_USE_SSL,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if settings.STORAGE_FORCE_PATH_STYLE else "auto"},
            ),
        )

    def resolve_local_path(self, object_key: str) -> Path:
        """Resolve object_key under local_root; reject path traversal."""
        root = self.local_root.resolve()
        candidate = (root / object_key).resolve()
        if not candidate.is_relative_to(root):
            raise ObjectStorageError("Invalid object key")
        return candidate

    async def ensure_bucket(self) -> None:
        if self._uses_local:
            await asyncio.to_thread(self.local_root.mkdir, parents=True, exist_ok=True)
            return
        if not self.is_configured or not settings.STORAGE_AUTO_CREATE_BUCKET:
            return

        def _ensure_bucket() -> None:
            try:
                self._client.head_bucket(Bucket=settings.STORAGE_BUCKET)
            except Exception:
                create_kwargs: dict[str, object] = {"Bucket": settings.STORAGE_BUCKET}
                if settings.STORAGE_REGION != "us-east-1":
                    create_kwargs["CreateBucketConfiguration"] = {
                        "LocationConstraint": settings.STORAGE_REGION
                    }
                self._client.create_bucket(**create_kwargs)

        try:
            await asyncio.to_thread(_ensure_bucket)
        except Exception as exc:
            logger.warning("failed to ensure storage bucket %s: %s", settings.STORAGE_BUCKET, exc)

    async def upload_bytes(self, *, object_key: str, body: bytes, content_type: str) -> str:
        if not self.is_configured:
            raise StorageNotConfiguredError("Object storage is not configured")

        if self._uses_local:

            def _write_local() -> None:
                dest = self.resolve_local_path(object_key)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(body)

            await asyncio.to_thread(_write_local)
            return self.public_url_for(object_key)

        def _upload() -> None:
            self._client.put_object(
                Bucket=settings.STORAGE_BUCKET,
                Key=object_key,
                Body=body,
                ContentType=content_type,
            )

        await asyncio.to_thread(_upload)
        return self.public_url_for(object_key)

    async def upload_file(
        self,
        *,
        object_key: str,
        file_path: Path,
        content_type: str,
    ) -> str:
        """Stream a local file to object storage without loading it into RAM."""
        if not self.is_configured:
            raise StorageNotConfiguredError("Object storage is not configured")
        path = Path(file_path)
        if not path.is_file():
            raise ObjectStorageError(f"Upload source file not found: {path}")

        if self._uses_local:

            def _copy_local() -> None:
                dest = self.resolve_local_path(object_key)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)

            await asyncio.to_thread(_copy_local)
            return self.public_url_for(object_key)

        def _upload() -> None:
            # Prefer multipart-capable file upload so large MP4s are not buffered.
            self._client.upload_file(
                Filename=str(path),
                Bucket=settings.STORAGE_BUCKET,
                Key=object_key,
                ExtraArgs={"ContentType": content_type},
            )

        await asyncio.to_thread(_upload)
        return self.public_url_for(object_key)

    async def delete_object(self, object_key: str | None) -> None:
        if not self.is_configured or not object_key:
            return

        if self._uses_local:

            def _delete_local() -> None:
                try:
                    path = self.resolve_local_path(object_key)
                except ObjectStorageError:
                    return
                if path.is_file():
                    path.unlink(missing_ok=True)

            try:
                await asyncio.to_thread(_delete_local)
            except Exception as exc:
                logger.warning("failed to delete local storage object %s: %s", object_key, exc)
            return

        def _delete() -> None:
            self._client.delete_object(Bucket=settings.STORAGE_BUCKET, Key=object_key)

        try:
            await asyncio.to_thread(_delete)
        except Exception as exc:
            logger.warning("failed to delete storage object %s: %s", object_key, exc)

    async def delete_prefix(self, *, prefix: str) -> None:
        """Delete all objects under prefix (local directory or S3 key prefix)."""
        if not self.is_configured or not prefix:
            return
        normalized = prefix.strip().strip("/")
        if not normalized:
            return

        if self._uses_local:

            def _delete_tree() -> None:
                try:
                    root = self.resolve_local_path(normalized)
                except ObjectStorageError:
                    return
                if root.is_dir():
                    shutil.rmtree(root, ignore_errors=True)
                elif root.is_file():
                    root.unlink(missing_ok=True)

            try:
                await asyncio.to_thread(_delete_tree)
            except Exception as exc:
                logger.warning("failed to delete local storage prefix %s: %s", normalized, exc)
            return

        def _delete_s3_prefix() -> None:
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=settings.STORAGE_BUCKET, Prefix=f"{normalized}/"):
                objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
                if not objects:
                    continue
                self._client.delete_objects(
                    Bucket=settings.STORAGE_BUCKET,
                    Delete={"Objects": objects, "Quiet": True},
                )

        try:
            await asyncio.to_thread(_delete_s3_prefix)
        except Exception as exc:
            logger.warning("failed to delete storage prefix %s: %s", normalized, exc)

    def public_url_for(self, object_key: str) -> str:
        if self._uses_local:
            # Ignore the S3/MinIO default public base when using filesystem storage.
            base = (settings.STORAGE_PUBLIC_BASE_URL or "").strip()
            if base and "/media" in base:
                return f"{base.rstrip('/')}/{object_key}"
            return f"{settings.API_V1_PREFIX.rstrip('/')}/media/{object_key}"
        if settings.STORAGE_PUBLIC_BASE_URL:
            return f"{settings.STORAGE_PUBLIC_BASE_URL.rstrip('/')}/{object_key}"
        if settings.STORAGE_ENDPOINT_URL:
            return (
                f"{settings.STORAGE_ENDPOINT_URL.rstrip('/')}/{settings.STORAGE_BUCKET}/{object_key}"
            )
        return f"https://{settings.STORAGE_BUCKET}.s3.amazonaws.com/{object_key}"

    def signed_url_for(self, object_key: str, expires_in: int | None = None) -> str:
        if not self.is_configured:
            raise StorageNotConfiguredError("Object storage is not configured")
        if self._uses_local:
            return self.public_url_for(object_key)
        return cast(str, self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.STORAGE_BUCKET, "Key": object_key},
            ExpiresIn=expires_in or settings.STORAGE_SIGNED_URL_EXPIRES_SECONDS,
        ))


object_storage = ObjectStorage()
