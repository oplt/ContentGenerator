from celery import Celery

from backend.core.config import settings


celery_app = Celery(
    "content_generator_backend",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["backend.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_expires=settings.CELERY_RESULT_EXPIRES_SECONDS,
    broker_connection_retry_on_startup=True,
    task_track_started=True,
    task_ignore_result=False,
    timezone="UTC",
    enable_utc=True,
    task_default_queue=settings.CELERY_QUEUE_GENERATION,
    task_routes={
        "backend.workers.tasks.send_email_task": {"queue": settings.CELERY_QUEUE_EMAIL},
        "backend.workers.tasks.poll_sources_task": {"queue": settings.CELERY_QUEUE_INGESTION},
        "backend.workers.tasks.ingest_source_task": {"queue": settings.CELERY_QUEUE_INGESTION},
        "backend.workers.tasks.generate_content_task": {"queue": settings.CELERY_QUEUE_GENERATION},
        "backend.workers.tasks.send_approval_task": {"queue": settings.CELERY_QUEUE_APPROVALS},
        "backend.workers.tasks.publish_due_jobs_task": {"queue": settings.CELERY_QUEUE_PUBLISHING},
        "backend.workers.tasks.sync_analytics_task": {"queue": settings.CELERY_QUEUE_ANALYTICS},
    },
)
