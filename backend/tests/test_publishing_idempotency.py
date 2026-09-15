"""Unit tests for publish attempt boundaries, failure classes, and stub idempotency."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi import HTTPException

from backend.modules.publishing.failure_classification import PublishErrorClass, classify_publish_error
from backend.modules.publishing.models import PublishingAttemptStatus, PublishingJob, PublishingJobStatus
from backend.modules.publishing.providers import StubPublishingProvider
from backend.modules.publishing.service import PublishingService


def test_classify_timeout_is_ambiguous() -> None:
    assert classify_publish_error(httpx.TimeoutException("timed out")) == PublishErrorClass.AMBIGUOUS


def test_classify_429_is_transient() -> None:
    request = httpx.Request("POST", "https://example.test/tweet")
    response = httpx.Response(429, request=request)
    exc = httpx.HTTPStatusError("rate limited", request=request, response=response)
    assert classify_publish_error(exc) == PublishErrorClass.TRANSIENT


def test_classify_400_is_permanent() -> None:
    request = httpx.Request("POST", "https://example.test/tweet")
    response = httpx.Response(400, request=request)
    exc = httpx.HTTPStatusError("bad request", request=request, response=response)
    assert classify_publish_error(exc) == PublishErrorClass.PERMANENT


def test_classify_http_exception_422_permanent() -> None:
    assert classify_publish_error(HTTPException(status_code=422, detail="blocked")) == PublishErrorClass.PERMANENT


def test_stub_provider_is_deterministic_for_attempt_key() -> None:
    provider = StubPublishingProvider("x")
    account = SimpleNamespace(id=uuid4(), handle="demo", account_external_id="demo")

    async def _run() -> None:
        first = await provider.publish_now(
            social_account=account,  # type: ignore[arg-type]
            assets=[],
            publish_attempt_key="job:attempt:1",
        )
        second = await provider.publish_now(
            social_account=account,  # type: ignore[arg-type]
            assets=[],
            publish_attempt_key="job:attempt:1",
        )
        assert first.external_post_id == second.external_post_id
        assert first.external_post_id is not None

    asyncio.run(_run())


def test_build_attempt_key_is_stable() -> None:
    job = PublishingJob(
        tenant_id=uuid4(),
        content_job_id=uuid4(),
        platform="x",
        idempotency_key="content-1:x",
        status=PublishingJobStatus.PENDING.value,
    )
    assert PublishingService.build_attempt_key(job, 1) == "content-1:x:attempt:1"
    assert PublishingService.build_attempt_key(job, 2) == "content-1:x:attempt:2"


def test_stale_claim_recovery_paths_documented_in_statuses() -> None:
    assert PublishingAttemptStatus.PREPARED.value == "prepared"
    assert PublishingAttemptStatus.AMBIGUOUS.value == "ambiguous"
    assert PublishingJobStatus.MANUAL_REQUIRED.value == "manual_required"


def test_claim_lease_defaults_are_positive() -> None:
    from backend.core.config import settings

    assert settings.PUBLISHING_CLAIM_LEASE_SECONDS > 0
    assert settings.PUBLISHING_MAX_ATTEMPTS >= 1
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=settings.PUBLISHING_CLAIM_LEASE_SECONDS)
    assert expires > now
