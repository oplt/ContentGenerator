from celery import signals
from typing import Any

from backend.db.session import dispose_engine
from backend.workers import runtime


@signals.worker_process_init.connect
def init_worker_process(**kwargs: Any) -> None:
    """Bind domain metrics / exporters inside each forked worker process."""
    from backend.core.logging import setup_logging
    from backend.core.telemetry import setup_telemetry

    setup_logging()
    setup_telemetry(app=None)


@signals.worker_process_shutdown.connect
def shutdown_worker_process(**kwargs: Any) -> None:
    loop = runtime._worker_loop
    if loop and not loop.is_closed():
        from backend.core.http import close_http_client

        loop.run_until_complete(close_http_client())
        loop.run_until_complete(dispose_engine())
        loop.close()
        runtime._worker_loop = None
