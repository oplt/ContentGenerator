"""Tests for bounded DB pool settings and entrypoint transaction ownership."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import asyncio

from sqlalchemy.pool import NullPool

from backend.core.config import Settings
from backend.db.session import _engine_kwargs, get_pool_stats, reset_pool_stats
from backend.db.transactions import session_scope
from backend.workers.runtime import run_async_task_simple


def test_api_pool_bounds_are_documented_and_positive() -> None:
    settings = Settings(
        DB_POOL_USE_NULL=False,
        DB_POOL_PROCESS_ROLE="api",
        DB_POOL_SIZE=5,
        DB_POOL_MAX_OVERFLOW=10,
    )
    assert settings.effective_db_pool_size == 5
    assert settings.effective_db_pool_max_overflow == 10
    assert settings.db_pool_max_connections_per_process == 15


def test_worker_pool_uses_smaller_defaults() -> None:
    settings = Settings(
        DB_POOL_PROCESS_ROLE="worker",
        DB_POOL_SIZE=5,
        DB_POOL_MAX_OVERFLOW=10,
        DB_POOL_WORKER_SIZE=2,
        DB_POOL_WORKER_MAX_OVERFLOW=2,
    )
    assert settings.effective_db_pool_size == 2
    assert settings.db_pool_max_connections_per_process == 4


def test_engine_kwargs_null_pool_escape_hatch() -> None:
    with patch("backend.db.session.settings") as mock_settings:
        mock_settings.DB_POOL_USE_NULL = True
        mock_settings.SQL_ECHO = False
        kwargs = _engine_kwargs()
    assert kwargs["poolclass"] is NullPool
    assert "pool_size" not in kwargs


def test_engine_kwargs_bounded_queue_pool() -> None:
    with patch("backend.db.session.settings") as mock_settings:
        mock_settings.DB_POOL_USE_NULL = False
        mock_settings.SQL_ECHO = False
        mock_settings.effective_db_pool_size = 3
        mock_settings.effective_db_pool_max_overflow = 4
        mock_settings.DB_POOL_TIMEOUT_SECONDS = 12.0
        mock_settings.DB_POOL_RECYCLE_SECONDS = 600
        kwargs = _engine_kwargs()
    assert kwargs["pool_size"] == 3
    assert kwargs["max_overflow"] == 4
    assert kwargs["pool_timeout"] == 12.0
    assert kwargs["pool_recycle"] == 600
    assert "poolclass" not in kwargs


def test_pool_stats_reset() -> None:
    reset_pool_stats()
    stats = get_pool_stats()
    assert stats["checkout"] == 0
    assert set(stats) >= {"connect", "checkout", "checkin", "invalidate"}


def test_run_async_task_simple_rolls_back_on_error() -> None:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    maker = MagicMock(return_value=session)

    async def boom(_db):
        raise RuntimeError("boom")

    with patch("backend.workers.runtime.get_sessionmaker", return_value=maker):
        try:
            run_async_task_simple(boom)
            raise AssertionError("expected RuntimeError")
        except RuntimeError as exc:
            assert str(exc) == "boom"

    session.rollback.assert_awaited()
    session.commit.assert_not_awaited()


def test_session_scope_commits_on_success() -> None:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    async def _run() -> None:
        with patch("backend.db.transactions.SessionLocal", return_value=session):
            async with session_scope() as db:
                assert db is session
        session.commit.assert_awaited()
        session.rollback.assert_not_awaited()

    asyncio.run(_run())
