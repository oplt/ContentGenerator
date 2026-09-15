"""Serve locally stored object-storage files (STORAGE_BACKEND=local)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from backend.core.storage import ObjectStorageError, object_storage

router = APIRouter()


@router.get("/{object_key:path}", include_in_schema=False)
async def serve_local_media(object_key: str) -> FileResponse:
    if not object_storage._uses_local:  # noqa: SLF001 — intentional gate for local backend only
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        path = object_storage.resolve_local_path(object_key)
    except ObjectStorageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Object not found")
    return FileResponse(path)
