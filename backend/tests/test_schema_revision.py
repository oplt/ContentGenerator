"""Schema revision gate — refuse work when DB behind Alembic head."""

from __future__ import annotations

import pytest

from backend.db import schema_revision
from backend.db.schema_revision import (
    SchemaRevisionError,
    SchemaRevisionStatus,
    assert_schema_at_head,
    check_schema_revision,
    expected_heads,
)


def test_expected_heads_single() -> None:
    heads = expected_heads()
    assert len(heads) == 1
    assert heads[0]


def test_check_schema_revision_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    heads = expected_heads()
    monkeypatch.setattr(
        schema_revision,
        "read_current_revision",
        lambda engine=None: heads[0],
    )
    status = check_schema_revision()
    assert status.ok
    assert status.current == heads[0]


def test_check_schema_revision_behind(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        schema_revision,
        "read_current_revision",
        lambda engine=None: "c9d0e1f2a3b4",
    )
    status = check_schema_revision()
    assert not status.ok
    assert "make migrate" in status.detail
    assert status.current == "c9d0e1f2a3b4"


def test_assert_schema_at_head_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schema_revision.settings, "SCHEMA_REVISION_ENFORCE", True)
    monkeypatch.setattr(
        schema_revision,
        "check_schema_revision",
        lambda: SchemaRevisionStatus(
            ok=False,
            current="old",
            expected_heads=("new",),
            detail="behind",
        ),
    )
    with pytest.raises(SchemaRevisionError, match="behind"):
        assert_schema_at_head(role="test")


def test_assert_schema_skipped_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schema_revision.settings, "SCHEMA_REVISION_ENFORCE", False)
    status = assert_schema_at_head(role="test")
    assert status.ok
    assert "skipped" in status.detail
