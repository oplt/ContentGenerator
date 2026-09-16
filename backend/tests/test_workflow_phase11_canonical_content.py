"""Phase 11 — canonical content model (GenerateText vs ContentJob)."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.content_generation.canonical import (
    canonical_primary_platform,
    extract_canonical_text,
)
from backend.modules.content_generation.models import GeneratedAssetType
from backend.modules.workflows.context import build_node_context
from backend.modules.workflows.nodes import IMPLEMENTED_SLICE
from backend.modules.workflows.nodes.canonical_content import (
    GenerateCanonicalContentConfig,
    GenerateCanonicalContentInput,
    GenerateCanonicalContentNode,
)
from backend.modules.workflows.nodes.platform_transform import (
    PlatformTransformConfig,
    PlatformTransformInput,
    PlatformTransformNode,
)
from backend.modules.workflows.nodes.text import GenerateTextNode
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.testing_support import (
    GENERATION_NODE_TYPES,
    mock_generation_result,
)


def _db() -> MagicMock:
    return MagicMock(spec=AsyncSession)


@pytest.fixture(autouse=True)
def _registry() -> Any:
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


def test_artifact_layers_are_distinct_in_registry() -> None:
    types = {cls.type for cls in IMPLEMENTED_SLICE}
    assert "generate_text" in types
    assert "generate_canonical_content" in types
    assert GenerateTextNode.type == "generate_text"
    assert GenerateCanonicalContentNode.type == "generate_canonical_content"
    assert "ContentJob" in GenerateCanonicalContentNode.description
    assert "ContentJob" in GenerateTextNode.description


def test_extract_canonical_prefers_writer_stage() -> None:
    assets = [
        SimpleNamespace(
            asset_type=GeneratedAssetType.TEXT_VARIANT.value,
            platform="x",
            text_content="platform variant",
        ),
        SimpleNamespace(
            asset_type=GeneratedAssetType.WRITER_STAGE.value,
            platform=None,
            text_content="  editorial body  ",
        ),
    ]
    assert extract_canonical_text(assets, primary_platform="x") == "editorial body"


def test_extract_canonical_falls_back_to_primary_platform_variant() -> None:
    assets = [
        SimpleNamespace(
            asset_type=GeneratedAssetType.TEXT_VARIANT.value,
            platform="instagram",
            text_content="ig copy",
        ),
        SimpleNamespace(
            asset_type=GeneratedAssetType.TEXT_VARIANT.value,
            platform="x",
            text_content="x copy",
        ),
    ]
    assert extract_canonical_text(assets, primary_platform="x") == "x copy"


def test_canonical_primary_platform_from_grounding() -> None:
    job = SimpleNamespace(
        grounding_bundle={
            "inference_trace": {"planner_platforms": ["linkedin", "x"]},
        },
        provider_metadata={},
    )
    assert canonical_primary_platform(job) == "linkedin"


def test_mock_generation_covers_canonical_node() -> None:
    assert "generate_canonical_content" in GENERATION_NODE_TYPES
    result = mock_generation_result(
        "generate_canonical_content",
        {"content_plan_id": "00000000-0000-4000-8000-000000000099"},
    )
    assert result.status.value == "succeeded"
    assert result.output["content_job_id"]
    assert "mock canonical" in result.output["text"]


def test_generate_canonical_content_wraps_service() -> None:
    async def _run() -> None:
        plan_id = uuid.uuid4()
        job_id = uuid.uuid4()
        job = MagicMock()
        job.id = job_id
        job.content_plan_id = plan_id
        job.status = "completed"
        job.target_social_account_ids = []
        job.grounding_bundle = {"risk_label": "low"}
        job.provider_metadata = {}

        asset = SimpleNamespace(
            asset_type=GeneratedAssetType.WRITER_STAGE.value,
            platform=None,
            text_content="Canonical editorial from orchestration",
        )

        svc = MagicMock()
        svc.generate = AsyncMock(return_value=job)
        svc.repo.list_assets = AsyncMock(return_value=[asset])
        svc.repo.get_asset_group_for_job = AsyncMock(return_value=None)

        db = _db()
        db.flush = AsyncMock()
        ctx = build_node_context(tenant_id=uuid.uuid4(), db=db)

        with patch(
            "backend.modules.content_generation.service.ContentGenerationService",
            return_value=svc,
        ):
            result = await GenerateCanonicalContentNode().execute(
                ctx,
                GenerateCanonicalContentInput(content_plan_id=plan_id),
                GenerateCanonicalContentConfig(),
            )

        assert result.status.value == "succeeded"
        assert result.output["content_job_id"] == str(job_id)
        assert result.output["text"] == "Canonical editorial from orchestration"
        assert job.grounding_bundle["canonical_text"] == (
            "Canonical editorial from orchestration"
        )
        svc.generate.assert_awaited_once()

    asyncio.run(_run())


def test_generate_canonical_content_maps_http_errors() -> None:
    async def _run() -> None:
        svc = MagicMock()
        svc.generate = AsyncMock(
            side_effect=HTTPException(status_code=422, detail="brief required")
        )
        ctx = build_node_context(tenant_id=uuid.uuid4(), db=_db())
        with patch(
            "backend.modules.content_generation.service.ContentGenerationService",
            return_value=svc,
        ):
            result = await GenerateCanonicalContentNode().execute(
                ctx,
                GenerateCanonicalContentInput(content_plan_id=uuid.uuid4()),
                GenerateCanonicalContentConfig(),
            )
        assert result.status.value == "failed"
        assert result.error is not None
        assert result.error["code"] == "content_generation_failed"
        assert "brief required" in result.error["message"]

    asyncio.run(_run())


def test_platform_transform_loads_canonical_from_job() -> None:
    async def _run() -> None:
        tenant_id = uuid.uuid4()
        job_id = uuid.uuid4()
        account_id = uuid.uuid4()
        job = MagicMock()
        job.id = job_id
        job.grounding_bundle = {"canonical_text": "From ContentJob grounding"}
        job.provider_metadata = {}

        account = MagicMock()
        account.id = account_id
        account.platform = "x"
        account.capability_flags = {}
        account.settings = {}

        repo = MagicMock()
        repo.get_job = AsyncMock(return_value=job)
        repo.list_assets = AsyncMock(return_value=[])

        pub_repo = MagicMock()
        pub_repo.get_social_accounts_by_ids = AsyncMock(return_value=[account])

        db = _db()
        ctx = build_node_context(tenant_id=tenant_id, db=db)

        with (
            patch(
                "backend.modules.content_generation.repository.ContentGenerationRepository",
                return_value=repo,
            ),
            patch(
                "backend.modules.publishing.repository.PublishingRepository",
                return_value=pub_repo,
            ),
            patch(
                "backend.modules.content_generation.variant_store.ContentVariantStore"
            ) as store_cls,
        ):
            store = store_cls.return_value
            store.upsert_variant = AsyncMock(
                side_effect=lambda **kwargs: SimpleNamespace(id=uuid.uuid4())
            )
            result = await PlatformTransformNode().execute(
                ctx,
                PlatformTransformInput(
                    content_job_id=job_id,
                    social_account_ids=[account_id],
                ),
                PlatformTransformConfig(),
            )

        assert result.status.value == "succeeded"
        assert result.output["canonical_text"] == "From ContentJob grounding"
        assert result.output["fingerprint_count"] == 1

    asyncio.run(_run())
