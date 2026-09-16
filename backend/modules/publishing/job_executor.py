from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, NoReturn, Protocol, cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.domain_metrics import domain_metrics
from backend.core.security import decrypt_secret, resolve_secret_reference
from backend.modules.content_generation.repository import ContentGenerationRepository
from backend.modules.publishing.account_ops import consume_publish_quota
from backend.modules.publishing.attempt_lifecycle import PublishAttemptLifecycle
from backend.modules.publishing.failure_classification import PublishErrorClass, classify_publish_error
from backend.modules.publishing.models import PublishingJob, PublishingJobStatus
from backend.modules.publishing.providers import get_provider
from backend.modules.publishing.repository import PublishingRepository


class _PublishJobDeps(Protocol):
    db: AsyncSession
    repo: PublishingRepository
    content_repo: ContentGenerationRepository
    attempts: PublishAttemptLifecycle


async def _maybe_defer_rate_limit(
    svc: _PublishJobDeps,
    tenant_id: UUID,
    job: PublishingJob,
    *,
    commit_boundaries: bool,
) -> PublishingJob | None:
    """Return job if deferred for quota; None if publishing may proceed."""
    if not job.social_account_id:
        return None
    prefetched = await svc.repo.get_social_account(tenant_id, job.social_account_id)
    if prefetched is None:
        return None
    quota = await consume_publish_quota(tenant_id=tenant_id, account=prefetched)
    if quota.allowed:
        return None

    now = datetime.now(timezone.utc)
    job.status = PublishingJobStatus.SCHEDULED.value
    job.scheduled_for = now + timedelta(seconds=quota.retry_after_seconds)
    job.claimed_at = None
    job.claim_expires_at = None
    job.worker_id = None
    job.provider_payload = {
        **(job.provider_payload or {}),
        "account_rate_limited": "true",
        "social_account_id": str(prefetched.id),
        "retry_after_seconds": str(quota.retry_after_seconds),
        "next_retry_at": job.scheduled_for.isoformat(),
    }
    domain_metrics.record_publish_rate_limited(platform=str(job.platform or "unknown"))
    await svc.db.flush()
    if commit_boundaries:
        await svc.db.commit()
    return job


async def _fail_and_raise(
    svc: _PublishJobDeps,
    *,
    job: PublishingJob,
    attempt: Any,
    exc: HTTPException,
    error_class: PublishErrorClass,
    commit_boundaries: bool,
) -> NoReturn:
    await svc.attempts.finalize_failure(
        job=job, attempt=attempt, exc=exc, error_class=error_class
    )
    if commit_boundaries:
        await svc.db.commit()
    raise exc


def _resolve_access_token(token_row: Any) -> str:
    access_token = decrypt_secret(token_row.access_token_encrypted) if token_row else ""
    if access_token.startswith("secret-ref:"):
        access_token = resolve_secret_reference(access_token.partition(":")[2]) or ""
    return access_token


def _risk_label_from_content_job(content_job: Any) -> str:
    grounding = (
        content_job.grounding_bundle
        if isinstance(getattr(content_job, "grounding_bundle", None), dict)
        else {}
    )
    risk_review = cast(dict[str, Any], grounding.get("risk_review", {}))
    return str(risk_review.get("label") or grounding.get("risk_label") or "low")


async def _resolve_publish_assets(
    svc: _PublishJobDeps,
    *,
    tenant_id: UUID,
    job: PublishingJob,
    assets: list[Any],
) -> list[Any]:
    """Prefer durable ContentVariant snapshot over generation-time TEXT_VARIANT assets."""
    from backend.modules.content_generation.variant_store import (
        ContentVariantStore,
        assets_from_variant_snapshot,
        snapshot_from_provider_payload,
    )

    snapshot = snapshot_from_provider_payload(job.provider_payload)
    if snapshot is None and getattr(job, "content_variant_id", None):
        snapshot = await ContentVariantStore(svc.db).get_snapshot(
            tenant_id, job.content_variant_id
        )
    if snapshot is None:
        return assets
    return assets_from_variant_snapshot(snapshot, media_assets=assets)


def _record_video_duration_metrics(job: PublishingJob, assets: list[Any]) -> None:
    for asset in assets:
        if asset.asset_type != "video":
            continue
        meta = getattr(asset, "metadata_json", None) or getattr(asset, "asset_metadata", None) or {}
        if not isinstance(meta, dict):
            break
        raw_duration = meta.get("duration_ms") or meta.get("duration_seconds")
        try:
            duration_ms = float(raw_duration)
            if "duration_seconds" in meta and "duration_ms" not in meta:
                duration_ms *= 1000.0
            domain_metrics.record_video_duration(
                platform=str(job.platform or "unknown"),
                duration_ms=duration_ms,
            )
        except (TypeError, ValueError):
            pass
        break


async def _run_provider_publish(
    *,
    provider: Any,
    social_account: Any,
    assets: list[Any],
    attempt_key: str,
    use_stub: bool,
) -> tuple[Any, Any, Any]:
    validation = await provider.validate_auth(social_account=social_account)
    if not validation.is_valid and not use_stub:
        raise HTTPException(
            status_code=400, detail=validation.detail or "Publishing credentials are invalid"
        )
    draft = await provider.create_draft(social_account=social_account, assets=assets)
    result = await provider.publish_now(
        social_account=social_account,
        assets=assets,
        publish_attempt_key=attempt_key,
    )
    if not result.external_post_url and result.external_post_id:
        result.external_post_url = await provider.fetch_post_url(
            social_account=social_account,
            external_post_id=result.external_post_id,
            provider_payload=result.payload,
        )
    return validation, draft, result


async def publish_job(
    svc: _PublishJobDeps,
    tenant_id: UUID,
    job: PublishingJob,
    *,
    worker_id: str | None = None,
    commit_boundaries: bool = False,
) -> PublishingJob:
    """
    Publish one job with a durable attempt boundary.

    When commit_boundaries=True (worker path): commit after prepare and after finalize
    so provider I/O is never inside an open DB transaction holding the claim.
    """
    deferred = await _maybe_defer_rate_limit(
        svc, tenant_id, job, commit_boundaries=commit_boundaries
    )
    if deferred is not None:
        return deferred

    attempt = await svc.attempts.prepare_attempt(job, worker_id=worker_id)
    if commit_boundaries:
        await svc.db.commit()

    social_account = (
        await svc.repo.get_social_account(tenant_id, job.social_account_id)
        if job.social_account_id
        else None
    )
    if not social_account:
        await _fail_and_raise(
            svc,
            job=job,
            attempt=attempt,
            exc=HTTPException(status_code=400, detail="No connected social account for publishing job"),
            error_class=PublishErrorClass.PERMANENT,
            commit_boundaries=commit_boundaries,
        )

    content_job = await svc.content_repo.get_job(tenant_id, job.content_job_id)
    if not content_job:
        await _fail_and_raise(
            svc,
            job=job,
            attempt=attempt,
            exc=HTTPException(status_code=404, detail="Content job not found"),
            error_class=PublishErrorClass.PERMANENT,
            commit_boundaries=commit_boundaries,
        )

    if _risk_label_from_content_job(content_job) == "blocked":
        blocked = HTTPException(
            status_code=422, detail="Risk review blocked this content from publishing"
        )
        await _fail_and_raise(
            svc,
            job=job,
            attempt=attempt,
            exc=blocked,
            error_class=PublishErrorClass.PERMANENT,
            commit_boundaries=commit_boundaries,
        )

    assets = await svc.content_repo.list_assets(content_job.id)
    assets = await _resolve_publish_assets(svc, tenant_id=tenant_id, job=job, assets=assets)
    token_row = await svc.repo.get_token_for_account(social_account.id) if social_account.id else None
    access_token = _resolve_access_token(token_row)
    use_stub = social_account.account_metadata.get("mode") == "stub"
    provider = get_provider(
        job.platform,
        use_stub=use_stub,
        access_token=access_token,
        account_external_id=social_account.account_external_id or "",
        dry_run=job.dry_run,
    )

    try:
        validation, draft, result = await _run_provider_publish(
            provider=provider,
            social_account=social_account,
            assets=assets,
            attempt_key=attempt.attempt_key,
            use_stub=use_stub,
        )
    except Exception as exc:
        error_class = classify_publish_error(exc)
        await svc.attempts.finalize_failure(
            job=job, attempt=attempt, exc=exc, error_class=error_class
        )
        if commit_boundaries:
            await svc.db.commit()
        raise

    post_type = "video" if any(asset.asset_type == "video" for asset in assets) else "text"
    job.provider = provider.platform
    await svc.attempts.finalize_success(
        tenant_id=tenant_id,
        job=job,
        attempt=attempt,
        social_account=social_account,
        result=result,
        draft_preview=draft.preview_text,
        draft_status=draft.status,
        auth_status=validation.account_status,
        publish_attempt_key=attempt.attempt_key,
        post_type=post_type,
    )
    if post_type == "video":
        _record_video_duration_metrics(job, assets)
    if commit_boundaries:
        await svc.db.commit()
    return job
