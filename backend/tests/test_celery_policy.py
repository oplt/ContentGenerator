"""Unit tests for Celery execution policy (T3.1)."""

from __future__ import annotations

from fastapi import HTTPException
import httpx

from backend.workers import tasks as task_module
from backend.workers.celery_app import celery_app
from backend.workers.task_policy import (
    TASK_POLICIES,
    TRANSIENT_EXCEPTIONS,
    WORKER_QUEUE_GROUPS,
    celery_task_kwargs,
    queue_csv_for_workload,
)


def test_all_registered_tasks_have_policies() -> None:
    registered = {
        name
        for name in celery_app.tasks
        if name.startswith("backend.workers.tasks.")
    }
    assert registered == set(TASK_POLICIES)


def test_no_task_autoretries_broad_exception() -> None:
    for name, policy in TASK_POLICIES.items():
        kwargs = celery_task_kwargs(name)
        autoretry = kwargs.get("autoretry_for", ())
        assert Exception not in autoretry
        assert BaseException not in autoretry
        if policy.max_retries == 0:
            assert autoretry == ()
        else:
            assert autoretry == TRANSIENT_EXCEPTIONS


def test_permanent_errors_are_not_transient() -> None:
    assert HTTPException not in TRANSIENT_EXCEPTIONS
    assert ValueError not in TRANSIENT_EXCEPTIONS
    assert httpx.TransportError in TRANSIENT_EXCEPTIONS


def test_time_limits_soft_before_hard() -> None:
    for name, policy in TASK_POLICIES.items():
        assert policy.soft_time_limit < policy.time_limit, name
        task = celery_app.tasks[name]
        assert task.soft_time_limit == policy.soft_time_limit
        assert task.time_limit == policy.time_limit


def test_acks_late_only_for_idempotent_tasks() -> None:
    assert TASK_POLICIES["backend.workers.tasks.send_email_task"].acks_late is False
    assert TASK_POLICIES["backend.workers.tasks.generate_content_task"].acks_late is False
    assert TASK_POLICIES["backend.workers.tasks.publish_due_jobs_task"].acks_late is True
    assert TASK_POLICIES["backend.workers.tasks.ingest_source_task"].acks_late is True
    assert celery_app.tasks["backend.workers.tasks.publish_due_jobs_task"].acks_late is True


def test_reject_on_worker_lost_enabled() -> None:
    assert celery_app.conf.task_reject_on_worker_lost is True
    for name in TASK_POLICIES:
        assert celery_app.tasks[name].reject_on_worker_lost is True


def test_prefetch_multiplier_is_bounded() -> None:
    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_queue_groups_are_disjoint_across_critical_paths() -> None:
    io = set(WORKER_QUEUE_GROUPS["io"])
    llm = set(WORKER_QUEUE_GROUPS["llm"])
    media = set(WORKER_QUEUE_GROUPS["media"])
    publishing = set(WORKER_QUEUE_GROUPS["publishing"])
    db = set(WORKER_QUEUE_GROUPS["db"])
    assert not (io & llm)
    assert not (io & publishing)
    assert not (llm & publishing)
    assert media.isdisjoint(io | llm | publishing | db)
    assert db.isdisjoint(io | llm | publishing | media)
    assert "publishing" in publishing
    assert "generation" in llm
    assert "video" in media
    assert "analytics" in db
    assert "analytics" not in io


def test_queue_csv_helper() -> None:
    assert queue_csv_for_workload("publishing") == "publishing"
    assert "ingestion" in queue_csv_for_workload("io")
    assert queue_csv_for_workload("db") == "analytics"


def test_media_tasks_route_to_video_queue() -> None:
    routes = celery_app.conf.task_routes
    assert routes["backend.workers.tasks.generate_image_asset_task"]["queue"] == "video"
    assert routes["backend.workers.tasks.generate_tts_asset_task"]["queue"] == "video"
    assert TASK_POLICIES["backend.workers.tasks.generate_image_asset_task"].workload == "media"
    assert TASK_POLICIES["backend.workers.tasks.sync_analytics_task"].workload == "db"


def test_task_routes_cover_all_policies() -> None:
    routes = celery_app.conf.task_routes
    for name in TASK_POLICIES:
        assert name in routes
        assert "queue" in routes[name]


def test_poll_sources_task_documents_fanout() -> None:
    doc = task_module.poll_sources_task.__doc__ or ""
    assert "Fan-out" in doc or "fan-out" in doc.lower()
    assert TASK_POLICIES["backend.workers.tasks.poll_sources_task"].soft_time_limit <= 60
