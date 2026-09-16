"""Phase 9 — canonical content + late platform specialization."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from typing import cast
from uuid import UUID

import pytest

from backend.modules.publishing.account_selection import group_by_fingerprint, variant_fingerprint
from backend.modules.publishing.models import SocialAccount
from backend.modules.workflows.context import build_node_context
from backend.modules.workflows.nodes import IMPLEMENTED_SLICE
from backend.modules.workflows.nodes.platform_transform import (
    PlatformTransformConfig,
    PlatformTransformInput,
    PlatformTransformNode,
)
from backend.modules.workflows.platform_adapt import adapt_canonical_for_platform, trim_text
from backend.modules.workflows.registry import build_default_registry, reset_default_registry


@pytest.fixture(autouse=True)
def _fresh_registry() -> Iterator[None]:
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


class _FakeAccount:
    def __init__(self, platform: str, settings: dict | None = None) -> None:
        self.id = uuid.uuid4()
        self.platform = platform
        self.capability_flags = {"text": "true"}
        self.settings = dict(settings or {})


def test_implemented_slice_includes_platform_transform() -> None:
    types = {cls.type for cls in IMPLEMENTED_SLICE}
    assert "platform_transform" in types
    assert "generate_text" in types


def test_adapt_x_trims_and_shares_fingerprint_group() -> None:
    a1 = _FakeAccount("x")
    a2 = _FakeAccount("x")  # same caps/settings → same fingerprint
    assert variant_fingerprint(a1) == variant_fingerprint(a2)  # type: ignore[arg-type]
    groups = group_by_fingerprint(cast(list[SocialAccount], [a1, a2]))
    assert len(groups) == 1
    fp = next(iter(groups))
    long = "word " * 80
    adapted = adapt_canonical_for_platform(
        canonical_text=long,
        platform="x",
        fingerprint=fp,
        social_account_ids=[str(a1.id), str(a2.id)],
        hashtags=["chess"],
    )
    assert len(adapted.text) <= 280
    assert adapted.platform == "x"
    assert len(adapted.social_account_ids) == 2


def test_adapt_youtube_splits_title_and_description() -> None:
    adapted = adapt_canonical_for_platform(
        canonical_text="Deep dive into endgames. More analysis follows here.",
        platform="youtube",
        fingerprint="youtube:abc",
        social_account_ids=[str(uuid.uuid4())],
        title="A very long youtube title that should be trimmed down for the platform limit",
        hashtags=["chess", "endgame"],
    )
    assert adapted.title is not None
    assert len(adapted.title) <= 95
    assert adapted.description is not None
    assert "#" in adapted.text or "chess" in (adapted.tags or [])


def test_trim_text_ellipsis() -> None:
    assert trim_text("hello world", 5) == "hell…"
    assert trim_text("hi", 10) == "hi"


def test_platform_transform_node_one_variant_per_fingerprint() -> None:
    async def _run() -> None:
        x1 = str(uuid.uuid4())
        x2 = str(uuid.uuid4())
        ig = str(uuid.uuid4())
        snapshot = {
            "accounts": [
                {
                    "social_account_id": x1,
                    "platform": "x",
                    "capability_flags": {},
                    "variant_fingerprint": "x:same",
                },
                {
                    "social_account_id": x2,
                    "platform": "x",
                    "capability_flags": {},
                    "variant_fingerprint": "x:same",
                },
                {
                    "social_account_id": ig,
                    "platform": "instagram",
                    "capability_flags": {},
                    "variant_fingerprint": "instagram:other",
                },
            ]
        }
        ctx = build_node_context(
            tenant_id=uuid.uuid4(),
            snapshot=snapshot,
        )
        node = PlatformTransformNode()
        result = await node.execute(
            ctx,
            PlatformTransformInput(
                text="Canonical editorial body about a historic chess game.",
                hashtags=["chess"],
                social_account_ids=[UUID(x1), UUID(x2), UUID(ig)],
            ),
            PlatformTransformConfig(),
        )
        assert result.status.value == "succeeded"
        variants = result.output["variants"]
        assert result.output["fingerprint_count"] == 2
        platforms = {v["platform"] for v in variants}
        assert platforms == {"x", "instagram"}
        x_variant = next(v for v in variants if v["platform"] == "x")
        assert set(x_variant["social_account_ids"]) == {x1, x2}

    asyncio.run(_run())
