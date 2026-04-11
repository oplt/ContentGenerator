from celery import signals
from backend.db.session import dispose_engine
from backend.workers import runtime


@signals.worker_process_shutdown.connect
def shutdown_worker_process(**kwargs):
    loop = runtime._worker_loop
    if loop and not loop.is_closed():
        loop.run_until_complete(dispose_engine())
        loop.close()
        runtime._worker_loop = None