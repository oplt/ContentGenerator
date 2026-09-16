"""Phase 11 — reusable media / content workflow nodes."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.context import build_node_context
from backend.modules.workflows.engine_inputs import resolve_node_inputs
from backend.modules.workflows.nodes import IMPLEMENTED_SLICE
from backend.modules.workflows.nodes.audio import GenerateTTSNode
from backend.modules.workflows.nodes.base import NodeResultStatus, WorkflowNodeNotImplementedError
from backend.modules.workflows.nodes.chess import GenerateChessVideoNode
from backend.modules.workflows.nodes.fact_review import FactReviewNode
from backend.modules.workflows.nodes.image import GenerateImageNode
from backend.modules.workflows.nodes.text import GenerateScriptNode, SummarizeNode
from backend.modules.workflows.nodes.video import GenerateVideoNode
from backend.modules.workflows.registry import build_default_registry, reset_default_registry


@pytest.fixture(autouse=True)
def _fresh_registry() -> Iterator[None]:
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


class _FakeLLM:
    provider_name = "fake"

    async def summarize(self, prompt: str, *, max_words: int = 120) -> str:
        return f"SUM:{max_words}:{prompt[:20]}"

    async def generate_text(self, *args: Any, **kwargs: Any) -> str:
        return "generated"


def test_summarize_node_uses_llm() -> None:
    node = SummarizeNode()
    ctx = build_node_context(tenant_id=uuid.uuid4())

    async def _run() -> None:
        with patch(
            "backend.modules.workflows.nodes.text.get_llm_provider",
            return_value=_FakeLLM(),
        ):
            result = await node.execute(
                ctx,
                node.validate_inputs({"text": "Long article about chess openings."}),
                node.validate_config({"max_words": 40}),
            )
        assert result.status == NodeResultStatus.SUCCEEDED
        assert result.output["text"].startswith("SUM:40:")

    asyncio.run(_run())


def test_generate_script_from_headline() -> None:
    node = GenerateScriptNode()
    ctx = build_node_context(tenant_id=uuid.uuid4())

    async def _run() -> None:
        with patch(
            "backend.modules.workflows.nodes.text.get_video_providers",
        ) as providers:
            research = AsyncMock()
            research.build_digest = AsyncMock(return_value="DIGEST")
            script_provider = AsyncMock()
            script_provider.build_script = AsyncMock(return_value="SCRIPT BODY")
            providers.return_value = (
                research,
                script_provider,
                MagicMock(),
                MagicMock(),
                MagicMock(),
                MagicMock(),
            )
            result = await node.execute(
                ctx,
                node.validate_inputs({"headline": "Market surge", "summary": "Stocks up"}),
                node.validate_config({"tone": "calm"}),
            )
        assert result.status == NodeResultStatus.SUCCEEDED
        assert result.output["script"] == "SCRIPT BODY"
        assert result.output["digest"] == "DIGEST"

    asyncio.run(_run())


def test_fact_review_topic_mode() -> None:
    node = FactReviewNode()
    ctx = build_node_context(tenant_id=uuid.uuid4())

    async def _run() -> None:
        result = await node.execute(
            ctx,
            node.validate_inputs(
                {
                    "headline": "Election results update",
                    "summary": "Voters cast ballots",
                    "keywords": ["election"],
                }
            ),
            node.validate_config({"mode": "topic", "content_vertical": "politics"}),
        )
        assert result.status == NodeResultStatus.SUCCEEDED
        assert result.output["fail_closed"] is True
        assert "elections" in result.output["topic_categories"] or "politics" in result.output[
            "topic_categories"
        ]

    asyncio.run(_run())


def test_generate_image_requires_db() -> None:
    node = GenerateImageNode()
    ctx = build_node_context(tenant_id=uuid.uuid4())

    async def _run() -> None:
        result = await node.execute(
            ctx,
            node.validate_inputs(
                {
                    "content_job_id": uuid.uuid4(),
                    "headline": "Cover",
                    "primary_topic": "tech",
                }
            ),
            node.validate_config({}),
        )
        assert result.status == NodeResultStatus.FAILED
        assert result.error and result.error["code"] == "missing_db"

    asyncio.run(_run())


def test_generate_image_calls_service() -> None:
    node = GenerateImageNode()
    job_id = uuid.uuid4()
    ctx = build_node_context(tenant_id=uuid.uuid4(), db=MagicMock(spec=AsyncSession))

    async def _run() -> None:
        fake_asset = MagicMock()
        fake_asset.id = uuid.uuid4()
        fake_asset.public_url = "https://cdn.example/cover.png"
        fake_asset.storage_key = "tenants/x/cover.png"
        fake_asset.content_job_id = job_id
        fake_asset.mime_type = "image/png"
        with patch(
            "backend.modules.workflows.nodes.image.ImageGenerationService"
        ) as svc_cls:
            svc_cls.return_value.generate_for_job = AsyncMock(return_value=fake_asset)
            result = await node.execute(
                ctx,
                node.validate_inputs(
                    {
                        "content_job_id": job_id,
                        "headline": "Cover",
                        "primary_topic": "tech",
                    }
                ),
                node.validate_config({"platform": "x"}),
            )
        assert result.status == NodeResultStatus.SUCCEEDED
        assert result.output["skipped"] is False
        assert result.output["public_url"] == "https://cdn.example/cover.png"

    asyncio.run(_run())


def test_generate_tts_calls_service() -> None:
    node = GenerateTTSNode()
    job_id = uuid.uuid4()
    ctx = build_node_context(tenant_id=uuid.uuid4(), db=MagicMock(spec=AsyncSession))

    async def _run() -> None:
        with patch("backend.modules.workflows.nodes.audio.TTSService") as svc_cls:
            svc_cls.return_value.generate_for_job = AsyncMock(return_value=None)
            result = await node.execute(
                ctx,
                node.validate_inputs(
                    {"content_job_id": job_id, "headline": "Hello", "summary": "World"}
                ),
                node.validate_config({}),
            )
        assert result.status == NodeResultStatus.SUCCEEDED
        assert result.output["skipped"] is True

    asyncio.run(_run())


def test_generate_video_script_pipeline() -> None:
    node = GenerateVideoNode()
    ctx = build_node_context(tenant_id=uuid.uuid4())

    async def _run() -> None:
        with patch(
            "backend.modules.workflows.nodes.video.get_video_providers"
        ) as providers:
            research = AsyncMock()
            research.build_digest = AsyncMock(return_value="D")
            script_provider = AsyncMock()
            script_provider.build_script = AsyncMock(return_value="S")
            visual = AsyncMock()
            visual.build_storyboard = AsyncMock(return_value="SB")
            captions = AsyncMock()
            captions.build_captions = AsyncMock(return_value="C")
            providers.return_value = (
                research,
                script_provider,
                visual,
                MagicMock(),
                captions,
                MagicMock(),
            )
            result = await node.execute(
                ctx,
                node.validate_inputs({"headline": "Breaking"}),
                node.validate_config({"mode": "script_pipeline"}),
            )
        assert result.status == NodeResultStatus.SUCCEEDED
        assert result.output["script"] == "S"
        assert result.output["storyboard"] == "SB"

    asyncio.run(_run())


def test_generate_chess_video_create_and_enqueue() -> None:
    node = GenerateChessVideoNode()
    ctx = build_node_context(tenant_id=uuid.uuid4(), db=MagicMock(spec=AsyncSession))
    job = MagicMock()
    job.id = uuid.uuid4()
    job.status = "queued"
    job.video_public_url = None
    job.thumbnail_public_url = None
    job.render_fingerprint = "abc"
    job.move_count = 12

    async def _run() -> None:
        with patch(
            "backend.modules.workflows.nodes.chess.ChessVideoService"
        ) as svc_cls:
            instance = svc_cls.return_value
            instance.create = AsyncMock(return_value=job)
            instance.enqueue_job = MagicMock()
            result = await node.execute(
                ctx,
                node.validate_inputs({"source_text": "1. e4 e5 2. Nf3 Nc6"}),
                node.validate_config({"sync": False}),
            )
        assert result.status == NodeResultStatus.SUCCEEDED
        assert result.output["enqueued"] is True
        assert result.output["chess_video_job_id"] == str(job.id)
        instance.enqueue_job.assert_called_once()

    asyncio.run(_run())


def test_remaining_control_stub_still_raises() -> None:
    from backend.modules.workflows.nodes.triggers import ScheduleTriggerNode

    node = ScheduleTriggerNode()
    ctx = build_node_context(tenant_id=uuid.uuid4())

    async def _run() -> None:
        with pytest.raises(WorkflowNodeNotImplementedError):
            await node.execute(ctx, node.validate_inputs({}), node.validate_config({}))

    asyncio.run(_run())


def test_implemented_slice_includes_media_nodes() -> None:
    types = {cls.type for cls in IMPLEMENTED_SLICE}
    assert {
        "summarize",
        "generate_script",
        "fact_review",
        "generate_image",
        "generate_tts",
        "generate_video",
        "generate_chess_video",
    }.issubset(types)


def test_engine_inputs_map_chess_and_image() -> None:
    job_id = uuid.uuid4()
    chess = resolve_node_inputs(
        node_type="generate_chess_video",
        trigger_payload={},
        initial_inputs={"pgn": "1. e4 e5"},
        upstream_outputs=[],
    )
    assert chess["source_text"] == "1. e4 e5"
    image = resolve_node_inputs(
        node_type="generate_image",
        trigger_payload={},
        initial_inputs={
            "content_job_id": job_id,
            "text": "Headline",
            "keywords": ["ai", "chip"],
        },
        upstream_outputs=[],
    )
    assert image["headline"] == "Headline"
    assert image["keywords"] == "ai, chip"
