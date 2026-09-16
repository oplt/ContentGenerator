"""Phase 17 — workflow security (secrets strip + account authz)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.modules.workflows.security import (
    authorize_social_account_ids,
    sanitize_mapping,
    sanitize_workflow_graph,
)


def test_sanitize_workflow_graph_strips_secret_keys() -> None:
    graph = sanitize_workflow_graph(
        {
            "nodes": [
                {
                    "id": "publish",
                    "type": "publish",
                    "version": 1,
                    "config": {
                        "dry_run": True,
                        "oauth_token": "leak",
                        "api_key": "x",
                        "platforms": ["x"],
                    },
                }
            ],
            "edges": [],
            "metadata": {"refresh_token": "nope", "layout": {"publish": {"x": 1, "y": 2}}},
        }
    )
    cfg = graph.nodes[0].config
    assert cfg["dry_run"] is True
    assert cfg["platforms"] == ["x"]
    assert "oauth_token" not in cfg
    assert "api_key" not in cfg
    assert "refresh_token" not in graph.metadata
    assert graph.metadata["layout"]["publish"]["x"] == 1


def test_sanitize_mapping_recursive() -> None:
    cleaned = sanitize_mapping(
        {"ok": 1, "access_token": "x", "nested": {"bearer_token": "y", "keep": True}}
    )
    assert cleaned == {"ok": 1, "nested": {"keep": True}}


def test_authorize_social_accounts_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeRepo:
        def __init__(self, db):  # noqa: ANN001
            _ = db

        async def get_social_accounts_by_ids(self, tenant_id, ids):  # noqa: ANN001
            _ = tenant_id, ids
            return []

    monkeypatch.setattr(
        "backend.modules.workflows.security.PublishingRepository",
        _FakeRepo,
    )

    class _DB:
        pass

    async def _run() -> None:
        with pytest.raises(HTTPException) as exc:
            await authorize_social_account_ids(
                _DB(),  # type: ignore[arg-type]
                tenant_id=uuid4(),
                social_account_ids=[uuid4()],
            )
        assert exc.value.status_code == 403

    asyncio.run(_run())
