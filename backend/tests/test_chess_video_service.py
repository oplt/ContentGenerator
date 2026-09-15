"""Chess video service unit tests (validate + cache reuse)."""

from __future__ import annotations

import asyncio
import uuid

from backend.modules.chess_video.models import ChessVideoJob, ChessVideoJobStatus
from backend.modules.chess_video.schemas import ChessVideoValidateRequest
from backend.modules.chess_video.service import ChessVideoService


def test_validate_accepts_san() -> None:
    async def _run() -> None:
        class _Dummy:
            pass

        service = ChessVideoService(_Dummy())  # type: ignore[arg-type]
        result = await service.validate(
            ChessVideoValidateRequest(source_text="1. e4 e5 2. Nf3", input_format="san")
        )
        assert result.valid is True
        assert result.detected_format == "san"
        assert result.move_count == 3

    asyncio.run(_run())


def test_validate_rejects_illegal_move() -> None:
    async def _run() -> None:
        class _Dummy:
            pass

        service = ChessVideoService(_Dummy())  # type: ignore[arg-type]
        result = await service.validate(
            ChessVideoValidateRequest(source_text="1. e4 e5 2. Qh8", input_format="san")
        )
        assert result.valid is False
        assert result.errors

    asyncio.run(_run())


def test_create_reuses_cached_render_without_enqueue() -> None:
    src = ChessVideoJob(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        source_text="1. e4",
        status=ChessVideoJobStatus.COMPLETED.value,
        stage=ChessVideoJobStatus.COMPLETED.value,
        video_public_url="http://cdn/video.mp4",
        video_storage_key="k/video.mp4",
        thumbnail_public_url="http://cdn/thumb.png",
        thumbnail_storage_key="k/thumb.png",
        duration_seconds=3.0,
        width=720,
        height=1280,
        file_size_bytes=1234,
        renderer_version="1",
    )
    dst = ChessVideoJob(
        id=uuid.uuid4(),
        tenant_id=src.tenant_id,
        source_text="1. e4",
        status=ChessVideoJobStatus.QUEUED.value,
        stage=ChessVideoJobStatus.QUEUED.value,
    )
    ChessVideoService._copy_cached_outputs(dst, src)
    assert dst.status == ChessVideoJobStatus.COMPLETED.value
    assert dst.video_public_url == src.video_public_url
    assert dst.progress == 1.0


def test_retry_transitions_failed_job_to_queued() -> None:
    async def _run() -> None:
        class _Repo:
            def __init__(self) -> None:
                self.job = ChessVideoJob(
                    id=uuid.uuid4(),
                    tenant_id=uuid.uuid4(),
                    source_text="1. e4 e5",
                    status=ChessVideoJobStatus.FAILED.value,
                    stage=ChessVideoJobStatus.FAILED.value,
                    progress=0.4,
                    error_message="boom",
                )

            async def get_for_tenant(self, *, tenant_id, job_id):  # noqa: ANN001
                if tenant_id != self.job.tenant_id or job_id != self.job.id:
                    return None
                return self.job

        class _Db:
            async def flush(self) -> None:
                return None

        service = ChessVideoService(_Db())  # type: ignore[arg-type]
        repo = _Repo()
        service.repo = repo  # type: ignore[assignment]
        job = await service.retry(tenant_id=repo.job.tenant_id, job_id=repo.job.id)
        assert job.status == ChessVideoJobStatus.QUEUED.value
        assert job.stage == ChessVideoJobStatus.QUEUED.value
        assert job.progress == 0.0
        assert job.error_message is None

    asyncio.run(_run())


def test_process_job_persists_failure_before_reraise() -> None:
    async def _run() -> None:
        job = ChessVideoJob(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            source_text="1. e4 e5",
            status=ChessVideoJobStatus.QUEUED.value,
            stage=ChessVideoJobStatus.QUEUED.value,
            progress=0.0,
            input_format="san",
            orientation="white",
            render_preset="economy_vertical",
            seconds_per_move=1.0,
            include_coordinates=True,
            include_move_text=True,
        )
        commits: list[str] = []

        class _Repo:
            async def get_for_tenant(self, *, tenant_id, job_id):  # noqa: ANN001
                if tenant_id != job.tenant_id or job_id != job.id:
                    return None
                return job

            async def find_reusable_completed(self, **_kwargs):  # noqa: ANN003
                return None

        class _Db:
            async def rollback(self) -> None:
                return None

            async def commit(self) -> None:
                commits.append(job.status)

            async def flush(self) -> None:
                return None

        service = ChessVideoService(_Db())  # type: ignore[arg-type]
        service.repo = _Repo()  # type: ignore[assignment]

        async def boom(*_args, **_kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("storage down")

        service._set_progress = boom  # type: ignore[method-assign]

        try:
            await service.process_job(tenant_id=job.tenant_id, job_id=job.id)
            raise AssertionError("expected failure")
        except RuntimeError as exc:
            assert "storage down" in str(exc)

        assert job.status == ChessVideoJobStatus.FAILED.value
        assert job.error_message and "storage down" in job.error_message
        assert commits == [ChessVideoJobStatus.FAILED.value]

    asyncio.run(_run())


def test_delete_returns_storage_keys() -> None:
    async def _run() -> None:
        job = ChessVideoJob(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            source_text="1. e4 e5 2. Nf3",
            normalized_pgn="1. e4 e5 2. Nf3",
            status=ChessVideoJobStatus.COMPLETED.value,
            stage=ChessVideoJobStatus.COMPLETED.value,
            video_storage_key="tenants/t/video.mp4",
            thumbnail_storage_key="tenants/t/thumb.png",
        )
        deleted: list[ChessVideoJob] = []

        class _Repo:
            async def get_for_tenant(self, *, tenant_id, job_id):  # noqa: ANN001
                if tenant_id != job.tenant_id or job_id != job.id:
                    return None
                return job

            async def delete(self, row: ChessVideoJob) -> None:
                deleted.append(row)

        class _Db:
            pass

        service = ChessVideoService(_Db())  # type: ignore[arg-type]
        service.repo = _Repo()  # type: ignore[assignment]
        cleanup = await service.delete(tenant_id=job.tenant_id, job_id=job.id)
        assert cleanup["video_key"] == "tenants/t/video.mp4"
        assert cleanup["thumb_key"] == "tenants/t/thumb.png"
        assert cleanup["tenant_id"] == str(job.tenant_id)
        assert cleanup["job_id"] == str(job.id)
        assert deleted == [job]
        # Deleting the ORM row removes PGN/source_text with it.
        assert deleted[0].source_text == "1. e4 e5 2. Nf3"

    asyncio.run(_run())
