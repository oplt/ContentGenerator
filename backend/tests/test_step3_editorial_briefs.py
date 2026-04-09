"""
Tests for Step 3 — Editorial Briefs Module.

Covers:
- BriefStatus lifecycle transitions
- EditorialBriefService.generate_brief: idempotency, sets GENERATING→READY
- approve_brief / reject_brief: state transitions and conflict errors
- expire_stale_briefs: correctly marks expired READY briefs
- LLM output parsing: valid JSON, strips markdown fences
- Schema fields present on EditorialBriefResponse
- Router is registered at /api/v1/briefs
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.editorial_briefs.models import BriefStatus, EditorialBrief
from backend.modules.editorial_briefs.schemas import (
    BriefGenerateRequest,
    EditorialBriefResponse,
)
from backend.modules.editorial_briefs.service import EditorialBriefService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svc():
    svc = object.__new__(EditorialBriefService)
    svc.db = AsyncMock()
    svc.db.flush = AsyncMock()
    svc.repo = AsyncMock()
    svc.story_repo = AsyncMock()
    svc.llm = AsyncMock()
    return svc


def _cluster(worthy: bool = True, vertical: str = "general", risk: str = "safe"):
    c = MagicMock()
    c.id = uuid.uuid4()
    c.headline = "Test headline"
    c.summary = "Test summary"
    c.primary_topic = "test"
    c.content_vertical = vertical
    c.risk_level = risk
    c.worthy_for_content = worthy
    c.explainability = {"keywords": "test, headline"}
    return c


def _brief(status: str = BriefStatus.READY.value):
    b = MagicMock(spec=EditorialBrief)
    b.id = uuid.uuid4()
    b.tenant_id = uuid.uuid4()
    b.story_cluster_id = uuid.uuid4()
    b.brand_profile_id = None
    b.status = status
    b.headline = "Test headline"
    b.angle = "Test angle"
    b.talking_points = ["point 1", "point 2"]
    b.recommended_format = "text"
    b.target_platforms = ["x", "instagram"]
    b.tone_guidance = "authoritative"
    b.content_vertical = "general"
    b.risk_notes = ""
    b.risk_level = "safe"
    b.operator_note = None
    b.approved_by_user_id = None
    b.actioned_at = None
    b.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    b.telegram_short_id = None
    b.generation_trace = {}
    b.created_at = datetime.now(timezone.utc)
    b.updated_at = datetime.now(timezone.utc)
    b.deleted_at = None
    b.version = 1
    return b


# ---------------------------------------------------------------------------
# BriefStatus enum
# ---------------------------------------------------------------------------

def test_brief_status_values() -> None:
    assert BriefStatus.PENDING.value == "pending"
    assert BriefStatus.GENERATING.value == "generating"
    assert BriefStatus.READY.value == "ready"
    assert BriefStatus.APPROVED.value == "approved"
    assert BriefStatus.REJECTED.value == "rejected"
    assert BriefStatus.EXPIRED.value == "expired"


# ---------------------------------------------------------------------------
# generate_brief: idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_brief_returns_existing_ready_brief() -> None:
    svc = _svc()
    tenant_id = uuid.uuid4()
    existing = _brief(BriefStatus.READY.value)
    svc.repo.get_by_cluster = AsyncMock(return_value=existing)

    req = BriefGenerateRequest(story_cluster_id=existing.story_cluster_id)
    result = await svc.generate_brief(tenant_id, req)

    assert result is existing
    svc.story_repo.get_cluster.assert_not_called()


@pytest.mark.asyncio
async def test_generate_brief_returns_existing_approved_brief() -> None:
    svc = _svc()
    tenant_id = uuid.uuid4()
    existing = _brief(BriefStatus.APPROVED.value)
    svc.repo.get_by_cluster = AsyncMock(return_value=existing)

    req = BriefGenerateRequest(story_cluster_id=existing.story_cluster_id)
    result = await svc.generate_brief(tenant_id, req)

    assert result is existing


@pytest.mark.asyncio
async def test_generate_brief_recreates_after_rejection() -> None:
    svc = _svc()
    tenant_id = uuid.uuid4()
    cluster_id = uuid.uuid4()
    existing = _brief(BriefStatus.REJECTED.value)
    existing.story_cluster_id = cluster_id
    svc.repo.get_by_cluster = AsyncMock(return_value=existing)

    cluster = _cluster(worthy=True)
    cluster.id = cluster_id
    svc.story_repo.get_cluster = AsyncMock(return_value=cluster)

    new_brief = _brief(BriefStatus.GENERATING.value)
    new_brief.story_cluster_id = cluster_id
    svc.repo.create = AsyncMock(return_value=new_brief)

    llm_output = json.dumps({
        "angle": "Economy facing headwinds",
        "talking_points": ["point 1", "point 2"],
        "recommended_format": "text",
        "target_platforms": ["x"],
        "tone_guidance": "authoritative",
        "risk_notes": "",
    })
    svc.llm.generate = AsyncMock(return_value=llm_output)

    req = BriefGenerateRequest(story_cluster_id=cluster_id)
    result = await svc.generate_brief(tenant_id, req)

    svc.repo.create.assert_called_once()
    assert result.status == BriefStatus.READY.value


@pytest.mark.asyncio
async def test_generate_brief_raises_404_if_cluster_not_found() -> None:
    from fastapi import HTTPException
    svc = _svc()
    svc.repo.get_by_cluster = AsyncMock(return_value=None)
    svc.story_repo.get_cluster = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await svc.generate_brief(uuid.uuid4(), BriefGenerateRequest(story_cluster_id=uuid.uuid4()))
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_generate_brief_raises_422_if_not_worthy() -> None:
    from fastapi import HTTPException
    svc = _svc()
    cluster_id = uuid.uuid4()
    svc.repo.get_by_cluster = AsyncMock(return_value=None)
    svc.story_repo.get_cluster = AsyncMock(return_value=_cluster(worthy=False))

    with pytest.raises(HTTPException) as exc_info:
        await svc.generate_brief(uuid.uuid4(), BriefGenerateRequest(story_cluster_id=cluster_id))
    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# LLM output parsing
# ---------------------------------------------------------------------------

def test_parse_llm_output_valid_json() -> None:
    svc = _svc()
    data = {"angle": "test", "talking_points": ["a", "b"]}
    assert svc._parse_llm_output(json.dumps(data)) == data


def test_parse_llm_output_strips_markdown_fences() -> None:
    svc = _svc()
    data = {"angle": "economy turmoil", "talking_points": []}
    raw = f"```json\n{json.dumps(data)}\n```"
    result = svc._parse_llm_output(raw)
    assert result["angle"] == "economy turmoil"


def test_parse_llm_output_strips_plain_fences() -> None:
    svc = _svc()
    data = {"angle": "no fence"}
    raw = f"```\n{json.dumps(data)}\n```"
    assert svc._parse_llm_output(raw)["angle"] == "no fence"


# ---------------------------------------------------------------------------
# approve_brief
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approve_brief_transitions_to_approved() -> None:
    svc = _svc()
    tenant_id = uuid.uuid4()
    brief = _brief(BriefStatus.READY.value)
    svc.repo.get = AsyncMock(return_value=brief)

    result = await svc.approve_brief(tenant_id, brief.id, "Looks good", uuid.uuid4())

    assert result.status == BriefStatus.APPROVED.value
    assert result.operator_note == "Looks good"
    assert result.actioned_at is not None


@pytest.mark.asyncio
async def test_approve_brief_rejects_wrong_status() -> None:
    from fastapi import HTTPException
    svc = _svc()
    brief = _brief(BriefStatus.PENDING.value)
    svc.repo.get = AsyncMock(return_value=brief)

    with pytest.raises(HTTPException) as exc_info:
        await svc.approve_brief(uuid.uuid4(), brief.id, None, None)
    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# reject_brief
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reject_brief_transitions_to_rejected() -> None:
    svc = _svc()
    brief = _brief(BriefStatus.READY.value)
    svc.repo.get = AsyncMock(return_value=brief)

    result = await svc.reject_brief(uuid.uuid4(), brief.id, "Wrong angle", uuid.uuid4())

    assert result.status == BriefStatus.REJECTED.value
    assert result.operator_note == "Wrong angle"


@pytest.mark.asyncio
async def test_reject_brief_from_approved_allowed() -> None:
    svc = _svc()
    brief = _brief(BriefStatus.APPROVED.value)
    svc.repo.get = AsyncMock(return_value=brief)

    result = await svc.reject_brief(uuid.uuid4(), brief.id, "Changed mind", None)
    assert result.status == BriefStatus.REJECTED.value


# ---------------------------------------------------------------------------
# expire_stale_briefs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expire_stale_briefs_marks_past_expiry() -> None:
    svc = _svc()
    tenant_id = uuid.uuid4()

    expired_brief = _brief(BriefStatus.READY.value)
    expired_brief.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

    fresh_brief = _brief(BriefStatus.READY.value)
    fresh_brief.expires_at = datetime.now(timezone.utc) + timedelta(hours=12)

    svc.repo.list_by_tenant = AsyncMock(return_value=[expired_brief, fresh_brief])

    count = await svc.expire_stale_briefs(tenant_id)

    assert count == 1
    assert expired_brief.status == BriefStatus.EXPIRED.value
    assert fresh_brief.status == BriefStatus.READY.value  # unchanged


@pytest.mark.asyncio
async def test_expire_stale_briefs_returns_zero_when_none_expired() -> None:
    svc = _svc()
    fresh = _brief(BriefStatus.READY.value)
    fresh.expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
    svc.repo.list_by_tenant = AsyncMock(return_value=[fresh])

    count = await svc.expire_stale_briefs(uuid.uuid4())
    assert count == 0


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_editorial_brief_response_fields() -> None:
    fields = EditorialBriefResponse.model_fields
    for field in [
        "id", "tenant_id", "story_cluster_id", "status", "headline", "angle",
        "talking_points", "recommended_format", "target_platforms", "tone_guidance",
        "content_vertical", "risk_notes", "risk_level", "operator_note",
        "actioned_at", "expires_at",
    ]:
        assert field in fields, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# Router registration
# ---------------------------------------------------------------------------

def test_briefs_router_registered() -> None:
    from backend.api.router import api_router
    paths = [route.path for route in api_router.routes]
    brief_routes = [p for p in paths if "/briefs" in p]
    assert len(brief_routes) >= 1, "No /briefs routes found in api_router"


def test_briefs_router_has_regenerate_endpoint() -> None:
    from backend.api.router import api_router
    paths = [route.path for route in api_router.routes]
    assert any("/briefs" in p and "regenerate" in p for p in paths), \
        "No /briefs/{id}/regenerate route found"


# ---------------------------------------------------------------------------
# regenerate_brief
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_regenerate_brief_from_rejected() -> None:
    svc = _svc()
    brief = _brief(BriefStatus.REJECTED.value)
    svc.repo.get = AsyncMock(return_value=brief)

    cluster = _cluster(worthy=True)
    cluster.id = brief.story_cluster_id
    svc.story_repo.get_cluster = AsyncMock(return_value=cluster)

    llm_output = json.dumps({
        "angle": "New angle after rejection",
        "talking_points": ["a", "b", "c"],
        "recommended_format": "text",
        "target_platforms": ["x", "bluesky"],
        "tone_guidance": "concise",
        "risk_notes": "",
    })
    svc.llm.generate = AsyncMock(return_value=llm_output)

    result = await svc.regenerate_brief(uuid.uuid4(), brief.id, uuid.uuid4())

    assert result.status == BriefStatus.READY.value
    assert result.angle == "New angle after rejection"
    assert result.operator_note is None
    assert result.actioned_at is None


@pytest.mark.asyncio
async def test_regenerate_brief_blocks_if_generating() -> None:
    from fastapi import HTTPException
    svc = _svc()
    brief = _brief(BriefStatus.GENERATING.value)
    svc.repo.get = AsyncMock(return_value=brief)

    with pytest.raises(HTTPException) as exc_info:
        await svc.regenerate_brief(uuid.uuid4(), brief.id, None)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_regenerate_brief_from_approved_resets_state() -> None:
    """Even an approved brief can be re-generated (sends it back to READY for re-approval)."""
    svc = _svc()
    brief = _brief(BriefStatus.APPROVED.value)
    svc.repo.get = AsyncMock(return_value=brief)

    cluster = _cluster(worthy=True)
    cluster.id = brief.story_cluster_id
    svc.story_repo.get_cluster = AsyncMock(return_value=cluster)

    llm_output = json.dumps({
        "angle": "Revised angle",
        "talking_points": ["x"],
        "recommended_format": "text",
        "target_platforms": ["x"],
        "tone_guidance": "bold",
        "risk_notes": "",
    })
    svc.llm.generate = AsyncMock(return_value=llm_output)

    result = await svc.regenerate_brief(uuid.uuid4(), brief.id, uuid.uuid4())

    assert result.status == BriefStatus.READY.value  # back to ready, needs re-approval


# ---------------------------------------------------------------------------
# Brief enforcement in ContentGenerationService
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_content_generation_blocked_without_approved_brief() -> None:
    """generate() must raise 422 if no approved brief exists for the cluster."""
    from fastapi import HTTPException
    from unittest.mock import AsyncMock, MagicMock
    from backend.modules.content_generation.service import ContentGenerationService

    svc = object.__new__(ContentGenerationService)
    svc.db = AsyncMock()
    svc.repo = AsyncMock()
    svc.plan_repo = AsyncMock()
    svc.story_repo = AsyncMock()
    svc.audit = AsyncMock()
    svc.video_pipeline = AsyncMock()
    svc.llm = AsyncMock()

    plan = MagicMock()
    plan.decision = "generate"
    plan.story_cluster_id = uuid.uuid4()
    plan.id = uuid.uuid4()
    svc.plan_repo.get_content_plan = AsyncMock(return_value=plan)

    cluster = MagicMock()
    cluster.id = plan.story_cluster_id
    svc.story_repo.get_cluster = AsyncMock(return_value=cluster)

    # No brief — brief_repo.get_by_cluster returns None
    with patch(
        "backend.modules.editorial_briefs.repository.EditorialBriefRepository.get_by_cluster",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await svc.generate(tenant_id=uuid.uuid4(), plan_id=plan.id)
        assert exc_info.value.status_code == 422
        assert "approved editorial brief" in exc_info.value.detail


@pytest.mark.asyncio
async def test_content_generation_blocked_with_pending_brief() -> None:
    """generate() must raise 422 if brief exists but is not in APPROVED status."""
    from fastapi import HTTPException
    from unittest.mock import AsyncMock, MagicMock
    from backend.modules.content_generation.service import ContentGenerationService

    svc = object.__new__(ContentGenerationService)
    svc.db = AsyncMock()
    svc.repo = AsyncMock()
    svc.plan_repo = AsyncMock()
    svc.story_repo = AsyncMock()
    svc.audit = AsyncMock()
    svc.video_pipeline = AsyncMock()
    svc.llm = AsyncMock()

    plan = MagicMock()
    plan.decision = "generate"
    plan.story_cluster_id = uuid.uuid4()
    plan.id = uuid.uuid4()
    svc.plan_repo.get_content_plan = AsyncMock(return_value=plan)

    cluster = MagicMock()
    cluster.id = plan.story_cluster_id
    svc.story_repo.get_cluster = AsyncMock(return_value=cluster)

    ready_brief = _brief(BriefStatus.READY.value)  # ready but not approved
    with patch(
        "backend.modules.editorial_briefs.repository.EditorialBriefRepository.get_by_cluster",
        new=AsyncMock(return_value=ready_brief),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await svc.generate(tenant_id=uuid.uuid4(), plan_id=plan.id)
        assert exc_info.value.status_code == 422
