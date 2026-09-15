"""Compatibility facade — prefer repository_sessions.SessionRepositoryMixin."""

from __future__ import annotations

from backend.modules.identity_access.repository_sessions import SessionRepositoryMixin

__all__ = ["SessionRepositoryMixin"]
