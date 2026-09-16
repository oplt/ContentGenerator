"""Shared pytest fixtures for backend tests."""

from __future__ import annotations

import pytest

from backend.core.config import settings


@pytest.fixture(autouse=True)
def _workflow_inline_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests drain claimed nodes in-process (no Celery broker required)."""
    monkeypatch.setattr(settings, "WORKFLOW_INLINE_NODE_EXECUTION", True)
