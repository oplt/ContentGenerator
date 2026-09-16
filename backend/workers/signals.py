from celery import signals
from typing import Any

from backend.db.session import dispose_engine
from backend.workers import runtime


def _enforce_schema(role: str) -> None:
    from backend.db.schema_revision import SchemaRevisionError, assert_schema_at_head

    try:
        assert_schema_at_head(role=role)
    except SchemaRevisionError:
        # Celery must not process tasks / beat must not dispatch against drift.
        raise


@signals.celeryd_init.connect
def enforce_schema_on_worker_init(sender: Any = None, **kwargs: Any) -> None:
    _enforce_schema("celery-worker")


@signals.beat_init.connect
def enforce_schema_on_beat_init(sender: Any = None, **kwargs: Any) -> None:
    _enforce_schema("celery-beat")


@signals.worker_process_init.connect
def init_worker_process(**kwargs: Any) -> None:
    """Bind domain metrics / exporters inside each forked worker process."""
    from backend.core.logging import setup_logging
    from backend.core.telemetry import setup_telemetry

    setup_logging()
    setup_telemetry(app=None)
    # Prefork children also re-check (covers late fork after parent init).
    _enforce_schema("celery-worker-process")


@signals.worker_process_shutdown.connect
def shutdown_worker_process(**kwargs: Any) -> None:
    async def cleanup() -> None:
        from backend.core.cache import redis_cache
        from backend.core.http import close_http_client

        await close_http_client()
        await redis_cache.close()
        await dispose_engine()

    runtime.shutdown_worker_loop(cleanup)


@signals.task_failure.connect
def log_task_failure_once(
    sender: Any = None,
    task_id: str | None = None,
    exception: BaseException | None = None,
    einfo: Any = None,
    **kwargs: Any,
) -> None:
    """One structured application_error per Celery failure (no second traceback here)."""
    from backend.core.app_errors import log_application_error

    _ = einfo  # Celery already captured; we log sanitized message + type once.
    if exception is None:
        return
    task_name = getattr(sender, "name", None) if sender is not None else None
    log_application_error(
        exception,
        method="CELERY",
        route=task_name,
        path=task_name,
        status_code=500,
        error_code="task_failure",
        include_traceback=True,
        force=True,
        task_id=task_id,
        task_name=task_name,
    )
