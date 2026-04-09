from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.modules.approvals.service import ApprovalService
from backend.modules.fact_review.service import FactRiskReviewService
from backend.modules.publishing.service import PublishingService


def test_fact_review_detects_unsupported_claims_and_fail_closed_topic() -> None:
    service = FactRiskReviewService()
    article = MagicMock()
    article.title = "Officials confirm the election schedule"
    article.summary = "The vote is scheduled for next month."
    article.body = "Officials confirm the election schedule and deny fraud claims."
    article.canonical_url = "https://example.com/election"

    review = service.review_generated_package(
        content_vertical="politics",
        headline="Election update",
        summary="Officials confirm the election schedule",
        topic="Election update",
        topic_risk_level="sensitive",
        claims=["Officials confirm the election schedule", "International observers certified the result"],
        keywords=["election", "vote"],
        source_articles=[article],
        evidence_links=["https://example.com/election"],
        generated_texts={"x": "International observers certified the result and everyone must panic."},
        reviewer_issues=[],
    )

    assert review["risk_label"] == "blocked"
    assert review["policy_flags"]["fail_closed"] is True
    assert review["policy_flags"]["unsupported_claims"] >= 1
    assert review["policy_flags"]["harmful_framing"]


@pytest.mark.asyncio
async def test_approval_service_blocks_asset_approval_when_risk_review_is_blocked() -> None:
    svc = object.__new__(ApprovalService)
    svc.content_repo = AsyncMock()
    svc.content_service = MagicMock()
    svc.publish_service = MagicMock()
    svc.settings_service = AsyncMock()
    svc.story_repo = AsyncMock()
    svc.brief_repo = AsyncMock()
    svc.audit = AsyncMock()
    svc.db = AsyncMock()
    svc.repo = AsyncMock()

    job = MagicMock()
    job.id = uuid.uuid4()
    job.grounding_bundle = {"risk_review": {"label": "blocked"}}
    svc.content_repo.get_job = AsyncMock(return_value=job)

    with pytest.raises(HTTPException) as exc:
        await svc.send_for_approval(tenant_id=uuid.uuid4(), content_job_id=job.id, recipient=None)

    assert exc.value.status_code == 422
    svc.repo.create_request.assert_not_called()


@pytest.mark.asyncio
async def test_publishing_service_blocks_publish_when_risk_review_is_blocked() -> None:
    svc = object.__new__(PublishingService)
    svc.repo = AsyncMock()
    svc.content_repo = AsyncMock()
    svc.story_repo = AsyncMock()
    svc.audit = AsyncMock()
    svc.db = AsyncMock()

    social_account = MagicMock()
    social_account.id = uuid.uuid4()
    social_account.account_metadata = {"mode": "stub"}
    job = MagicMock()
    job.id = uuid.uuid4()
    job.platform = "x"
    job.social_account_id = social_account.id
    job.content_job_id = uuid.uuid4()

    content_job = MagicMock()
    content_job.id = job.content_job_id
    content_job.grounding_bundle = {"risk_review": {"label": "blocked"}}

    svc.repo.get_social_account = AsyncMock(return_value=social_account)
    svc.content_repo.get_job = AsyncMock(return_value=content_job)

    with pytest.raises(HTTPException) as exc:
        await svc._publish_job(uuid.uuid4(), job)

    assert exc.value.status_code == 422
