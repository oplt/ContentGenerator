"""Phase 10 — typed PlatformCapabilities + compiler capability checks."""

from __future__ import annotations

import uuid

from backend.modules.publishing.platform_capabilities import (
    flags_to_capabilities,
    platform_defaults,
    workflow_capability_tags,
)
from backend.modules.workflows.capability_context import enrich_compile_context
from backend.modules.workflows.compiler import WorkflowCompiler
from backend.modules.workflows.graph_schema import CompileContext
from backend.modules.workflows.registry import build_default_registry, reset_default_registry


def setup_function() -> None:
    reset_default_registry(build_default_registry())


def teardown_function() -> None:
    reset_default_registry(None)


def _video_graph() -> dict:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {"id": "video", "type": "generate_video", "version": 1, "config": {}},
        ],
        "edges": [{"source": "trigger", "target": "video"}],
    }


def _text_publish_graph() -> dict:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {
                "id": "generate",
                "type": "generate_text",
                "version": 1,
                "config": {"max_tokens": 100},
            },
            {"id": "publish", "type": "publish", "version": 1, "config": {"dry_run": True}},
        ],
        "edges": [
            {"source": "trigger", "target": "generate"},
            {"source": "generate", "target": "publish"},
        ],
    }


def test_flags_to_capabilities_x_provider_style() -> None:
    caps = flags_to_capabilities(
        {"text": "true", "video": "false", "thread": "true"},
        platform="x",
    )
    assert caps.supports_text is True
    assert caps.supports_video is False
    assert caps.supports_threads is True
    assert caps.max_text_length == 280
    assert "video" not in workflow_capability_tags(caps)


def test_youtube_defaults_support_video() -> None:
    caps = platform_defaults("youtube")
    assert caps.supports_video is True
    assert "video" in workflow_capability_tags(caps)


def test_compiler_rejects_video_for_x_only_account() -> None:
    account_id = uuid.uuid4()
    key = str(account_id)
    ctx = enrich_compile_context(
        CompileContext(social_account_ids=[account_id], require_publish_targets=False),
        platforms={key: "x"},
        flag_maps={key: {"text": "true", "video": "false", "thread": "true"}},
    )
    result = WorkflowCompiler().validate_graph(_video_graph(), ctx)
    assert result.valid is False
    assert any(e.code == "incompatible_capabilities" for e in result.errors)


def test_compiler_accepts_video_for_youtube_account() -> None:
    account_id = uuid.uuid4()
    key = str(account_id)
    ctx = enrich_compile_context(
        CompileContext(social_account_ids=[account_id], require_publish_targets=False),
        platforms={key: "youtube"},
    )
    result = WorkflowCompiler().validate_graph(_video_graph(), ctx)
    assert result.valid is True


def test_compiler_accepts_text_publish_on_x() -> None:
    account_id = uuid.uuid4()
    key = str(account_id)
    ctx = enrich_compile_context(
        CompileContext(social_account_ids=[account_id]),
        platforms={key: "x"},
        flag_maps={key: {"text": "true", "video": "false"}},
    )
    result = WorkflowCompiler().validate_graph(_text_publish_graph(), ctx)
    assert result.valid is True


def test_media_node_unknown_capabilities_when_unresolved() -> None:
    account_id = uuid.uuid4()
    ctx = CompileContext(
        social_account_ids=[account_id],
        require_publish_targets=False,
        require_capability_check=True,
    )
    result = WorkflowCompiler().validate_graph(_video_graph(), ctx)
    assert result.valid is False
    assert any(e.code == "unknown_capabilities" for e in result.errors)


def test_soft_skip_when_no_targets() -> None:
    result = WorkflowCompiler().validate_graph(
        _video_graph(), CompileContext(require_publish_targets=False)
    )
    assert result.valid is True
